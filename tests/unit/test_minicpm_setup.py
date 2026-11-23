import hashlib
import importlib.util
import json
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from pdf2docx_ai.cli import app
from pdf2docx_ai.config import Settings
from pdf2docx_ai.ocr.local_http import LocalHTTP,probe_model
from pdf2docx_ai.ocr.minicpm import MiniCPMOCR10Engine


def test_missing_server_has_one_actionable_message_and_diagnostics():
    engine=MiniCPMOCR10Engine(Settings())
    def unavailable(request): raise httpx.ConnectError("Connection refused",request=request)
    engine.transport._client=httpx.Client(transport=httpx.MockTransport(unavailable))
    health=engine.health_check()
    assert health["code"]=="server_unreachable"
    assert health["endpoint"]=="http://127.0.0.1:18499"
    assert "Avvia il server" in health["reason"]
    assert health["reason"].count("18499")==1
    assert len(health["diagnostics"])==1
    engine.shutdown()


def test_running_empty_ollama_is_distinguished_from_missing_server():
    transport=LocalHTTP("http://127.0.0.1:11434/v1")
    transport._client=httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,json={"models":[]})))
    health=probe_model(transport,"minicpm-ocr")
    assert not health["available"]
    assert health["code"]=="model_missing"
    assert "non è installato" in health["reason"]
    transport.close()


def load_setup():
    path=Path(__file__).parents[2]/"scripts"/"setup_minicpm.py"
    spec=importlib.util.spec_from_file_location("minicpm_setup",path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_setup_default_only_prints_plan_without_creating_models(tmp_path,monkeypatch,capsys):
    setup=load_setup()
    monkeypatch.setattr(setup,"WEIGHTS",tmp_path/"weights")
    monkeypatch.setattr(setup,"STORE",tmp_path/"ollama")
    assert setup.main([])==0
    plan=json.loads(capsys.readouterr().out)
    assert plan["downloads_started"] is False
    assert plan["total_download_bytes"]==2039908992
    assert not (tmp_path/"weights").exists()
    assert all(len(entry["sha256"])==64 for entry in plan["files"])


def test_verified_download_rejects_corruption_and_never_replaces_existing(tmp_path,monkeypatch):
    setup=load_setup();monkeypatch.setattr(setup,"WEIGHTS",tmp_path)
    entry={"name":"test.gguf","repository":"openbmb/test","revision":"immutable", "size":4,"sha256":hashlib.sha256(b"GGUF").hexdigest()}
    client=httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,content=b"GGUF")))
    setup.download(client,entry)
    assert setup.verified(tmp_path/"test.gguf",entry)
    (tmp_path/"test.gguf").write_bytes(b"oops")
    with pytest.raises(RuntimeError,match="nessuna sovrascrittura"): setup.download(client,entry)
    assert (tmp_path/"test.gguf").read_bytes()==b"oops"
    client.close()


def test_gui_serve_accepts_explicit_local_minicpm_endpoint(monkeypatch,tmp_path):
    import uvicorn
    import pdf2docx_ai.web.app as web
    calls={}
    def create_app(work_dir,settings): calls["settings"]=settings;return "test-app"
    monkeypatch.setattr(web,"create_app",create_app)
    monkeypatch.setattr(uvicorn,"run",lambda app,**kwargs:calls.update(kwargs))
    result=CliRunner().invoke(app,["serve","--minicpm-url","http://127.0.0.1:11434/v1","--minicpm-model","already-installed"])
    assert result.exit_code==0,result.output
    assert calls["settings"].minicpm_url=="http://127.0.0.1:11434/v1"
    assert calls["settings"].minicpm_model=="already-installed"
    assert calls["host"]=="127.0.0.1"
    bad=CliRunner().invoke(app,["serve","--minicpm-url","https://example.com/v1"])
    assert bad.exit_code!=0
