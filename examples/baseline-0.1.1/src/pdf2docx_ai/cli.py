from __future__ import annotations
import importlib.metadata
import json
import logging
import platform
from pathlib import Path
import sys
from concurrent.futures import ProcessPoolExecutor
from typing import Annotated

import typer
from pydantic import ValidationError

from . import __version__
from .config import Settings

app=typer.Typer(help="PDF2DOCX AI Fidelity · conversione interamente locale",no_args_is_help=True,pretty_exceptions_enable=False)


def _print(data,json_output=False):
    if json_output: typer.echo(json.dumps(data,ensure_ascii=False,indent=2))
    elif isinstance(data,dict):
        for k,v in data.items(): typer.echo(f"{k}: {json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v}")
    else: typer.echo(str(data))


def _failure(exc,json_output):
    logging.getLogger(__name__).error("%s",exc)
    if json_output: typer.echo(json.dumps({"error":str(exc),"type":type(exc).__name__},ensure_ascii=False))
    else: typer.echo(f"Errore: {exc}",err=True)
    raise typer.Exit(1)


@app.command()
def doctor(json_output: bool=typer.Option(False,"--json")):
    """Controlla ambiente e disponibilità locale senza scaricare modelli."""
    from .ocr.selector import engine_health
    from .quality.validator import find_renderer
    deps={}
    for name in ["PyMuPDF","python-docx","Pillow","numpy","pydantic","typer","fastapi","uvicorn","httpx","psutil"]:
        try: deps[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: deps[name]="missing"
    data=dict(application="PDF2DOCX AI Fidelity",version=__version__,python=sys.version.split()[0],
              platform=platform.platform(),architecture=platform.machine(),dependencies=deps,
              engines=engine_health(Settings()),renderer=find_renderer(),
              acceleration="Native extraction CPU; Vision managed by macOS; Metal only via separately installed verified runtime",
              downloads="disabled; installation of model weights always explicit")
    _print(data,json_output)


@app.command("inspect")
def inspect_command(input: Path,json_output: bool=typer.Option(False,"--json")):
    """Analizza tipo, dimensioni, colonne e rotazione del PDF."""
    from .pdf.inspector import inspect_pdf
    try: _print(inspect_pdf(input),json_output)
    except Exception as exc: _failure(exc,json_output)


@app.command("convert")
def convert_command(
    input: Path,
    output: Path|None=typer.Option(None,"--output","-o"),
    engine: str=typer.Option("auto","--engine"),
    mode: str=typer.Option("editable","--mode"),
    language: str=typer.Option("it","--language"),
    dpi: int=typer.Option(180,"--dpi"),
    max_pages: int=typer.Option(500,"--max-pages"),
    max_file_mb: int=typer.Option(100,"--max-file-mb"),
    timeout: float=typer.Option(180,"--timeout"),
    layout: str=typer.Option("geometric","--layout"),
    layout_model_dir: Path|None=typer.Option(None,"--layout-model-dir"),
    xiaomi_url: str=typer.Option("http://127.0.0.1:11434/v1","--xiaomi-url"),
    xiaomi_model: str=typer.Option("longwayxu/xiaomi-ocr-0:bf16","--xiaomi-model"),
    minicpm_url: str=typer.Option("http://127.0.0.1:18499/v1","--minicpm-url"),
    minicpm_model: str=typer.Option("minicpm-ocr","--minicpm-model"),
    validate_visual: bool=typer.Option(False,"--validate-visual"),
    searchable_pdf: bool=typer.Option(False,"--searchable-pdf"),
    ground_truth: Path|None=typer.Option(None,"--ground-truth"),
    second_engine: str|None=typer.Option(None,"--second-engine"),
    renderer: str|None=typer.Option(None,"--renderer"),
    resume: bool=typer.Option(True,"--resume/--no-resume"),
    overwrite: bool=typer.Option(False,"--overwrite"),
    json_output: bool=typer.Option(False,"--json"),
    verbose: bool=typer.Option(False,"--verbose"),
):
    """Converte PDF nativi, scansioni e pagine miste in Word e report."""
    from .pipeline import convert
    logging.basicConfig(level=logging.DEBUG if verbose else logging.WARNING,format="%(levelname)s %(message)s")
    try:
        settings=Settings(engine=engine,mode=mode,language=language,dpi=dpi,max_pages=max_pages,max_file_mb=max_file_mb,
                          ocr_timeout=timeout,layout=layout,layout_model_dir=layout_model_dir,xiaomi_url=xiaomi_url,
                          xiaomi_model=xiaomi_model,minicpm_url=minicpm_url,minicpm_model=minicpm_model,
                          validate_visual=validate_visual,searchable_pdf=searchable_pdf,ground_truth=ground_truth,
                          second_pass=bool(second_engine),second_engine=second_engine,renderer=renderer,resume=resume,overwrite=overwrite)
        target=output or input.with_name(input.stem+"."+mode+".docx")
        def progress(value,message):
            if not json_output: typer.echo(f"{value:5.0%} {message}",err=True)
        result=convert(input,target,settings,progress=progress)
        _print(result.model_dump(mode="json"),json_output)
    except Exception as exc: _failure(exc,json_output)


@app.command("compare")
def compare_command(input: Path,engines: str=typer.Option("xiaomi,minicpm","--engines"),
                    report: Path=typer.Option(Path("comparison.html"),"--report"),
                    language: str=typer.Option("it","--language"),
                    ground_truth: Path|None=typer.Option(None,"--ground-truth"),
                    overwrite: bool=typer.Option(False,"--overwrite"),
                    json_output: bool=typer.Option(False,"--json")):
    """Esegue due motori in sequenza e conserva entrambe le conversioni."""
    from .pipeline import compare
    try:
        names=engines.split(",")
        if any(n not in ("xiaomi","minicpm","vision","tesseract") for n in names): raise ValueError("Motore non riconosciuto")
        result=compare(input,report,Settings(language=language,ground_truth=ground_truth,overwrite=overwrite),names)
        _print(result.model_dump(mode="json"),json_output)
    except Exception as exc: _failure(exc,json_output)


def _benchmark_one(args):
    path,output,config=args
    from .pipeline import convert
    try:
        result=convert(Path(path),Path(output),Settings.model_validate(config))
        return {"file":str(path),"status":"ok",**result.model_dump(mode="json")}
    except Exception as exc: return {"file":str(path),"status":"failed","error":str(exc)}


@app.command("benchmark")
def benchmark_command(directory: Path,output: Path=typer.Option(Path("benchmark-output"),"--output"),
                      engine: str=typer.Option("auto","--engine"),workers: int=typer.Option(1,"--workers",min=1,max=8),
                      validate_visual: bool=typer.Option(False,"--validate-visual"),overwrite: bool=typer.Option(False,"--overwrite"),
                      json_output: bool=typer.Option(False,"--json")):
    """Misura fixture PDF, isolando i worker in processi separati."""
    from .pipeline import atomic_json
    try:
        files=sorted(directory.rglob("*.pdf"))
        if not files: raise ValueError("Nessun PDF nella directory")
        output=output.resolve();output.mkdir(parents=True,exist_ok=True)
        report_path=output/"benchmark.json"
        if report_path.exists() and not overwrite: raise FileExistsError(str(report_path))
        config=Settings(engine=engine,workers=workers,validate_visual=validate_visual,overwrite=overwrite).model_dump(mode="json")
        tasks=[(str(p),str(output/(str(p.relative_to(directory)).replace("/","_")+".docx")),config) for p in files]
        if workers==1: results=[_benchmark_one(t) for t in tasks]
        else:
            with ProcessPoolExecutor(max_workers=workers) as pool: results=list(pool.map(_benchmark_one,tasks))
        data=dict(python=sys.version.split()[0],platform=platform.platform(),workers=workers,engine=engine,
                  results=results,passed=sum(r["status"]=="ok" for r in results),failed=sum(r["status"]!="ok" for r in results))
        atomic_json(report_path,data);_print(data,json_output)
        if data["failed"]: raise typer.Exit(1)
    except typer.Exit: raise
    except Exception as exc: _failure(exc,json_output)


@app.command("serve")
def serve(port: int=typer.Option(8765,"--port",min=1024,max=65535),
          work_dir: Path|None=typer.Option(None,"--work-dir"),workers: int=typer.Option(1,"--workers",min=1,max=8),
          minicpm_url: str=typer.Option("http://127.0.0.1:18499/v1","--minicpm-url"),
          minicpm_model: str=typer.Option("minicpm-ocr","--minicpm-model"),
          xiaomi_url: str=typer.Option("http://127.0.0.1:11434/v1","--xiaomi-url"),
          xiaomi_model: str=typer.Option("longwayxu/xiaomi-ocr-0:bf16","--xiaomi-model")):
    """Avvia la GUI locale su http://127.0.0.1:8765."""
    import uvicorn
    from .web.app import create_app
    from .ocr.local_http import local_base_url
    try:
        local_base_url(minicpm_url);local_base_url(xiaomi_url)
    except ValueError as exc: _failure(exc,False)
    settings=Settings(workers=workers,minicpm_url=minicpm_url,minicpm_model=minicpm_model,
                      xiaomi_url=xiaomi_url,xiaomi_model=xiaomi_model)
    uvicorn.run(create_app(work_dir,settings),host="127.0.0.1",port=port,log_level="info")


if __name__=="__main__": app()
