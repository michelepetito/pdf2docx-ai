import importlib.util
from pathlib import Path
import os
import pytest
from pdf2docx_ai import system


def load_script(name):
    path=Path(__file__).parents[2]/'scripts'/(name+'.py')
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_windows_standard_paths_work_without_modifying_path(tmp_path,monkeypatch):
    root=tmp_path/'Program Files'
    for relative in ['LibreOffice/program/soffice.com','Tesseract-OCR/tesseract.exe']:
        path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'placeholder')
    monkeypatch.setattr(system.platform,'system',lambda:'Windows')
    monkeypatch.setattr(system.shutil,'which',lambda _:None)
    monkeypatch.setenv('ProgramFiles',str(root))
    assert system.find_program('soffice')==str(root/'LibreOffice/program/soffice.com')
    assert system.find_program('tesseract')==str(root/'Tesseract-OCR/tesseract.exe')
    # An invalid explicit renderer must not silently use another program.
    assert system.find_program('soffice',str(tmp_path/'missing.exe')) is None


def test_portable_minicpm_refuses_busy_port_and_preserves_existing_pid(tmp_path,monkeypatch):
    script=load_script('serve_minicpm');monkeypatch.setattr(script,'STORE',tmp_path)
    pid=tmp_path/'server.pid';pid.write_text('existing-owner')
    monkeypatch.setattr(script.shutil,'which',lambda _: 'ollama')
    class BusySocket:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def bind(self,*args):raise OSError('occupied')
    monkeypatch.setattr(script.socket,'socket',BusySocket)
    with pytest.raises(RuntimeError,match='occupied'):script.main([])
    assert pid.read_text()=='existing-owner'


def test_registration_checks_process_liveness_without_os_kill(tmp_path,monkeypatch):
    script=load_script('setup_minicpm')
    monkeypatch.setattr(script,'STORE',tmp_path);monkeypatch.setattr(script,'WEIGHTS',tmp_path)
    (tmp_path/'server.pid').write_text(str(os.getpid()))
    monkeypatch.setattr(script.shutil,'which',lambda _: 'ollama')
    monkeypatch.setattr(script,'verified',lambda *args:True)
    monkeypatch.setattr(script.psutil,'pid_exists',lambda pid:pid==os.getpid())
    def forbidden(*args):raise AssertionError('os.kill(pid, 0) can terminate a Windows process')
    monkeypatch.setattr(script.os,'kill',forbidden)
    calls=[];monkeypatch.setattr(script.subprocess,'run',lambda argv,**kwargs:calls.append((argv,kwargs)))
    script.register({'files':[],'model_alias':'minicpm-ocr'})
    assert calls[0][0][1:3]==['create','minicpm-ocr']
    assert calls[0][1]['env']['OLLAMA_HOST']=='127.0.0.1:18499'
