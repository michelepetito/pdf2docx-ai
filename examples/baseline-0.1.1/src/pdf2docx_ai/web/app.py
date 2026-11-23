"""Loopback-only web UI with bounded uploads and private conversion jobs."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import logging
import math
from pathlib import Path
import shutil
import tempfile
import threading
import time
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.concurrency import run_in_threadpool

from pdf2docx_ai.config import Settings
from pdf2docx_ai.pdf.runtime import PDF_LOCK

logger = logging.getLogger(__name__)
ASSETS = Path(__file__).parent
MAX_JOBS = 32
RETENTION_SECONDS = 24 * 3600
CHUNK_SIZE = 1024 * 1024


class UploadLimitMiddleware:
    """Bound the HTTP body before multipart parsing spools the upload to disk."""

    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") != "POST":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        length = headers.get(b"content-length")
        try:
            too_large = length is not None and int(length) > self.max_bytes
        except ValueError:
            too_large = True
        if too_large:
            return await JSONResponse({"detail": "Caricamento oltre il limite consentito"}, status_code=413)(scope, receive, send)
        received = 0

        async def bounded_receive():
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > self.max_bytes:
                raise HTTPException(413, "Caricamento oltre il limite consentito")
            return message

        return await self.app(scope, bounded_receive, send)


def _convert(*args, **kwargs):
    from pdf2docx_ai.pipeline import convert
    return convert(*args, **kwargs)


def _engine_health(settings):
    from pdf2docx_ai.ocr.selector import engine_health
    return engine_health(settings)


@dataclass
class Job:
    id: str
    directory: Path
    filename: str
    status: str = "queued"
    progress: float = 0.0
    message: str = "In attesa"
    error: str | None = None
    created: float = field(default_factory=time.time)
    result: dict | None = None

    def public(self) -> dict:
        files = {"input": f"/api/jobs/{self.id}/files/input"}
        if self.status == "complete" and self.result:
            for kind, attr in FILE_FIELDS.items():
                if self.result.get(attr):
                    files[kind] = f"/api/jobs/{self.id}/files/{kind}"
        return {"id": self.id, "filename": self.filename, "status": self.status,
                "progress": self.progress, "message": self.message,
                "error": self.error, "files": files}


FILE_FIELDS = {"docx": "output_path", "report": "report_path", "json": "json_path",
               "model": "model_path", "searchable": "searchable_path"}
MEDIA_TYPES = {"input": "application/pdf", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
               "report": "text/html", "json": "application/json", "model": "application/json", "searchable": "application/pdf"}


def create_app(work_dir: Path | None = None, settings: Settings | None = None) -> FastAPI:
    """Build an isolated local application. Bind the server to 127.0.0.1 only.

    Uploaded PDFs and results live in a private session directory until server
    shutdown. ``work_dir`` chooses its parent, never a user-controlled job path.
    """
    defaults = settings or Settings()
    if work_dir is not None:
        work_dir = Path(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="pdf2docx-web-", dir=work_dir))
    root.chmod(0o700)
    jobs: dict[str, Job] = {}
    lock = threading.RLock()
    pool = ThreadPoolExecutor(max_workers=defaults.workers, thread_name_prefix="pdf2docx-web")
    active_uploads = 0

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
            shutil.rmtree(root, ignore_errors=True)

    app = FastAPI(title="PDF2DOCX AI Fidelity", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.jobs_root = root
    app.state.jobs = jobs
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "::1"])
    app.add_middleware(UploadLimitMiddleware, max_bytes=defaults.max_file_mb * 1024 * 1024 + CHUNK_SIZE)
    app.mount("/static", StaticFiles(directory=ASSETS / "static"), name="static")

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        # Host allowlisting rejects DNS rebinding; exact Origin matching also
        # blocks cross-origin browser submissions to the loopback service.
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin:
                parsed = urlsplit(origin)
                expected = f"{request.url.scheme}://{request.headers.get('host', '')}"
                if parsed.scheme not in {"http", "https"} or origin.rstrip("/") != expected:
                    return JSONResponse({"detail": "Origine della richiesta non autorizzata"}, status_code=403)
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "Richiesta cross-site non autorizzata"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; frame-src 'self' blob:; object-src 'none'; "
            "base-uri 'none'; form-action 'self'; frame-ancestors 'self'"
        )
        return response

    def find_job(job_id: str) -> Job:
        with lock:
            job = jobs.get(job_id)
            if job is None:
                raise HTTPException(404, "Conversione non trovata")
            return job

    def prune_jobs():
        now = time.time()
        for job_id, job in list(jobs.items()):
            if job.status in {"complete", "failed"} and now - job.created > RETENTION_SECONDS:
                shutil.rmtree(job.directory, ignore_errors=True)
                del jobs[job_id]

    def run_job(job: Job, options: Settings):
        def progress(value: float, message: str):
            with lock:
                numeric = float(value)
                job.progress = max(0.0, min(1.0, numeric)) if math.isfinite(numeric) else 0.0
                job.message = str(message)
        try:
            with lock:
                job.status = "running"
                job.message = "Analisi del documento"
            output = job.directory / f"documento.{options.mode}.docx"
            result = _convert(job.directory / "input.pdf", output, options, progress=progress)
            with lock:
                job.result = result.model_dump(mode="json")
                job.status = "complete"
                job.progress = 1.0
                job.message = "Conversione completata"
        except Exception as exc:
            logger.exception("Conversion job failed: %s", job.id)
            with lock:
                job.status = "failed"
                # Error text is inserted with textContent by the frontend.
                job.error = str(exc)
                job.message = "Conversione non riuscita"

    @app.get("/", response_class=HTMLResponse)
    def index():
        return (ASSETS / "templates" / "index.html").read_text(encoding="utf-8")

    @app.get("/api/settings")
    def public_settings():
        return {"max_file_mb": defaults.max_file_mb, "max_pages": defaults.max_pages,
                "engine": defaults.engine, "mode": defaults.mode, "language": defaults.language}

    @app.get("/api/engines")
    def engines():
        """Probe installed capabilities without loading or downloading models."""
        return {"engines": _engine_health(defaults)}

    @app.post("/api/jobs", status_code=202)
    async def create_job(file: UploadFile = File(...), engine: str = Form("auto"),
                         mode: str = Form("editable"), language: str = Form("it"),
                         validate_visual: bool = Form(False), searchable_pdf: bool = Form(False)):
        nonlocal active_uploads
        try:
            data = defaults.model_dump()
            data.update(engine=engine, mode=mode, language=language,
                        validate_visual=validate_visual, searchable_pdf=searchable_pdf,
                        overwrite=False, ground_truth=None)
            options = Settings.model_validate(data)
        except ValidationError:
            await file.close()
            raise HTTPException(422, "Motore, modalità o lingua non validi")
        with lock:
            prune_jobs()
            full = len(jobs) + active_uploads >= MAX_JOBS
            if not full:
                active_uploads += 1
        if full:
            await file.close()
            raise HTTPException(429, "Limite di conversioni della sessione raggiunto; riavviare il server")
        directory = root / uuid4().hex
        try:
            directory.mkdir(mode=0o700)
            size = 0
            with (directory / "input.pdf").open("xb") as stream:
                while chunk := await file.read(CHUNK_SIZE):
                    size += len(chunk)
                    if size > options.max_file_mb * 1024 * 1024:
                        raise HTTPException(413, f"PDF oltre il limite di {options.max_file_mb} MB")
                    stream.write(chunk)
            import pymupdf
            try:
                def validate_upload():
                    from pdf2docx_ai.pdf.inspector import open_pdf
                    with PDF_LOCK,open_pdf(directory/"input.pdf",options):
                        pass
                await run_in_threadpool(validate_upload)
            except Exception as exc:
                raise HTTPException(422, str(exc)) from exc
            # Display names are never used to construct filesystem paths.
            filename = (file.filename or "documento.pdf").replace("\\", "/").rsplit("/", 1)[-1][:180]
            job = Job(id=directory.name, directory=directory, filename=filename)
            with lock:
                jobs[job.id] = job
            pool.submit(run_job, job, options)
            return job.public()
        except BaseException:
            shutil.rmtree(directory, ignore_errors=True)
            raise
        finally:
            with lock:
                active_uploads -= 1
            await file.close()

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        with lock:
            return find_job(job_id).public()

    @app.get("/api/jobs/{job_id}/files/{kind}")
    def download(job_id: str, kind: str, download: bool = False):
        job = find_job(job_id)
        if kind == "input":
            path = job.directory / "input.pdf"
        elif kind in FILE_FIELDS and job.status == "complete" and job.result:
            value = job.result.get(FILE_FIELDS[kind])
            if not value:
                raise HTTPException(404, "File non disponibile")
            path = Path(value)
        else:
            raise HTTPException(404, "File non disponibile")
        try:
            path = path.resolve(strict=True)
            path.relative_to(job.directory.resolve())
        except (ValueError, OSError):
            raise HTTPException(404, "File non disponibile")
        if not path.is_file():
            raise HTTPException(404, "File non disponibile")
        return FileResponse(path, media_type=MEDIA_TYPES[kind], filename=path.name,
                            content_disposition_type="attachment" if download or kind in {"docx", "json", "model"} else "inline")

    @app.get("/api/jobs/{job_id}/preview/{page_number}")
    def preview(job_id: str, page_number: int):
        job = find_job(job_id)
        import pymupdf
        with PDF_LOCK,pymupdf.open(job.directory / "input.pdf") as pdf:
            if page_number < 1 or page_number > len(pdf):
                raise HTTPException(404, "Pagina non trovata")
            page = pdf[page_number - 1]
            area = page.rect.width * page.rect.height
            if area <= 0:
                raise HTTPException(422, "Dimensioni pagina non valide")
            scale = min(1.5, math.sqrt(defaults.max_pixels / area))
            pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
            return Response(pix.tobytes("png"), media_type="image/png")

    return app
