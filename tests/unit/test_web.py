from pathlib import Path
import time

from fastapi.testclient import TestClient
import pymupdf
import pytest

from pdf2docx_ai.config import Settings
from pdf2docx_ai.web import app as web


def pdf_bytes(pages=1):
    with pymupdf.open() as pdf:
        for _ in range(pages):
            page = pdf.new_page()
            page.insert_text((72, 72), "Documento di prova")
        return pdf.tobytes()


@pytest.fixture
def client(tmp_path, monkeypatch):
    class Result:
        def __init__(self, output):
            self.output = output

        def model_dump(self, mode="json"):
            result = {"output_path": str(self.output)}
            for key, suffix, content in [("report_path", ".html", "<h1>Qualità</h1>"),
                                         ("json_path", ".quality.json", "{}"),
                                         ("model_path", ".model.json", "{}")]:
                target = self.output.with_suffix(suffix)
                target.write_text(content)
                result[key] = str(target)
            result["searchable_path"] = None
            return result

    def convert(source, output, settings, progress=None):
        assert source.is_file()
        assert settings.engine == "auto"
        if progress:
            progress(0.5, "Ricostruzione")
        output.write_bytes(b"docx-placeholder-only-for-test")
        return Result(output)

    monkeypatch.setattr(web, "_convert", convert)
    app = web.create_app(tmp_path)
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        yield test_client
    assert not app.state.jobs_root.exists()


def await_job(client, job_id):
    for _ in range(100):
        state = client.get(f"/api/jobs/{job_id}").json()
        if state["status"] in {"complete", "failed"}:
            return state
        time.sleep(0.01)
    pytest.fail("Job failed to finish")


def test_web_job_and_downloads(client):
    index = client.get("/")
    assert index.status_code == 200
    assert "Tutto sul tuo dispositivo" in index.text
    assert index.headers["x-content-type-options"] == "nosniff"
    response = client.post("/api/jobs", files={"file": ("../../unsafe.pdf", pdf_bytes(), "application/pdf")})
    assert response.status_code == 202, response.text
    state = await_job(client, response.json()["id"])
    assert state["status"] == "complete", state
    assert state["filename"] == "unsafe.pdf"
    assert state["progress"] == 1
    assert client.get(state["files"]["docx"]).content.startswith(b"docx-placeholder")
    assert client.get(state["files"]["report"]).status_code == 200
    assert client.get(state["files"]["input"]).content.startswith(b"%PDF")
    preview = client.get(f"/api/jobs/{state['id']}/preview/1")
    assert preview.headers["content-type"] == "image/png"
    assert client.get(f"/api/jobs/{state['id']}/preview/2").status_code == 404
    assert client.get(f"/api/jobs/{state['id']}/files/secrets").status_code == 404


def test_web_rejects_invalid_and_oversized(client):
    assert client.post("/api/jobs", files={"file": ("bad.pdf", b"not pdf")}).status_code == 422
    assert client.post("/api/jobs", files={"file": ("valid.pdf", pdf_bytes())}, data={"engine": "remote-cloud"}).status_code == 422
    assert client.post("/api/jobs", content=b"x", headers={"content-length": str(200 * 1024 * 1024)}).status_code == 413
    assert client.get("/api/jobs/missing").status_code == 404


def test_web_rejects_cross_origin(client):
    assert client.post("/api/jobs", files={"file": ("document.pdf", pdf_bytes())}, headers={"origin": "https://attacker.example"}).status_code == 403
    assert client.get("/", headers={"host": "attacker.example"}).status_code == 400
    assert client.post("/api/jobs", files={"file": ("document.pdf", pdf_bytes())}, headers={"sec-fetch-site": "cross-site"}).status_code == 403


def test_web_page_limit(tmp_path):
    app = web.create_app(tmp_path, Settings(max_pages=1))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.post("/api/jobs", files={"file": ("large.pdf", pdf_bytes(2))})
        assert response.status_code == 422
        assert "pagine" in response.json()["detail"]


def test_web_rejects_chunked_body_before_multipart_spooling(tmp_path):
    app = web.create_app(tmp_path, Settings(max_file_mb=1))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.post("/api/jobs", content=iter([b"x" * (2 * 1024 * 1024 + 1)]),
                               headers={"content-type": "multipart/form-data; boundary=example"})
        assert response.status_code == 413


def test_web_conversion_error_is_reported(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("Modello OCR non disponibile")
    monkeypatch.setattr(web, "_convert", fail)
    with TestClient(web.create_app(tmp_path), base_url="http://127.0.0.1") as client:
        result = client.post("/api/jobs", files={"file": ("scan.pdf", pdf_bytes())})
        state = await_job(client, result.json()["id"])
        assert state["status"] == "failed"
        assert state["error"] == "Modello OCR non disponibile"
        assert "docx" not in state["files"]


def test_web_does_not_serve_outside_job(tmp_path, monkeypatch):
    class OutsideResult:
        def model_dump(self, mode="json"):
            return {"output_path": str(tmp_path / "outside.docx")}
    (tmp_path / "outside.docx").write_bytes(b"private")
    monkeypatch.setattr(web, "_convert", lambda *a, **kw: OutsideResult())
    with TestClient(web.create_app(tmp_path), base_url="http://127.0.0.1") as client:
        response = client.post("/api/jobs", files={"file": ("document.pdf", pdf_bytes())})
        state = await_job(client, response.json()["id"])
        assert client.get(state["files"]["docx"]).status_code == 404


def test_web_shows_real_engine_availability_without_starting_jobs(tmp_path,monkeypatch):
    probes=[]
    def health(settings):
        probes.append(settings.minicpm_url)
        return {"minicpm":{"available":False,"code":"server_unreachable","reason":"Server locale non attivo"},
                "vision":{"available":True}}
    monkeypatch.setattr(web,"_engine_health",health)
    with TestClient(web.create_app(tmp_path),base_url="http://127.0.0.1") as client:
        result=client.get("/api/engines")
        assert result.status_code==200
        assert result.json()["engines"]["minicpm"]["available"] is False
        assert probes==["http://127.0.0.1:18499/v1"]
        assert not client.app.state.jobs
        assert 'id="engine-status"' in client.get("/").text
