"""Explicit, repository-local MiniCPM setup. No downloads without its flag.

Default: print a reviewable plan. --download-models fetches pinned official
weights; --register imports them into the isolated server started by the
companion start-minicpm.command. No system installation or remote scripts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import psutil

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=Path(__file__).with_name("minicpm-models.json")
WEIGHTS=ROOT/"models"/"MiniCPM-OCR-1.0-gguf"
STORE=ROOT/"models"/"ollama"


def verified(path,entry):
    if not path.is_file() or path.stat().st_size!=entry["size"]:
        return False
    digest=hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024**2),b""): digest.update(chunk)
    return digest.hexdigest()==entry["sha256"]


def model_url(entry):
    return f'https://huggingface.co/{entry["repository"]}/resolve/{entry["revision"]}/{entry["name"]}'


def download(client,entry):
    destination=WEIGHTS/entry["name"]
    if destination.exists():
        if verified(destination,entry):
            print("Già verificato:",entry["name"])
            return
        raise RuntimeError(f"File esistente non conforme, nessuna sovrascrittura: {destination}")
    partial=destination.with_suffix(".gguf.part")
    offset=partial.stat().st_size if partial.exists() else 0
    if offset>entry["size"]: raise RuntimeError(f"Download parziale troppo grande: {partial}")
    headers={"Range":f"bytes={offset}-"} if offset else {}
    if offset<entry["size"]:
        with client.stream("GET",model_url(entry),headers=headers) as response:
            response.raise_for_status()
            append=offset>0 and response.status_code==206
            if append and not response.headers.get("content-range","").startswith(f"bytes {offset}-"):
                raise RuntimeError("Offset del download non corrispondente")
            received=offset if append else 0
            last=received//(100*1024**2)
            with partial.open("ab" if append else "wb") as stream:
                for chunk in response.iter_bytes(1024**2):
                    received+=len(chunk)
                    if received>entry["size"]: raise RuntimeError("Download oltre la dimensione ufficiale")
                    stream.write(chunk)
                    current=received//(100*1024**2)
                    if current>last:
                        print(f'{entry["name"]}: {received/entry["size"]:.0%}',flush=True);last=current
    if not verified(partial,entry):
        raise RuntimeError(f"Checksum/dimensione errati: {partial}. Il file non viene importato.")
    partial.replace(destination)
    print("SHA-256 verificato:",entry["name"])


def register(manifest):
    executable=shutil.which("ollama")
    if not executable: raise RuntimeError("Ollama non installato; nessuna installazione automatica")
    for entry in manifest["files"]:
        if not verified(WEIGHTS/entry["name"],entry):
            raise RuntimeError(f'Peso assente/non verificato: {entry["name"]}')
    # Only the companion launcher claims ownership of this repository-local
    # store. Do not register into an unrelated/default Ollama instance.
    pid_file=STORE/"server.pid"
    if not pid_file.is_file(): raise RuntimeError("Avvia prima python scripts/serve_minicpm.py")
    try:
        if not psutil.pid_exists(int(pid_file.read_text())):raise ValueError('Server PID not running')
    except (OSError,ValueError) as exc: raise RuntimeError("Server isolato non attivo; riavvia python scripts/serve_minicpm.py") from exc
    modelfile=WEIGHTS/"Modelfile"
    text="""FROM ./MiniCPM-OCR-1_0-Q8_0.gguf
FROM ./mmproj-model-f16-4x.gguf
DRAFT ./dspark-MiniCPM-OCR-1_0-Q8_0.gguf
REQUIRES 0.40.12
PARAMETER num_ctx 8192
PARAMETER temperature 0
PARAMETER draft_num_predict 15
"""
    if modelfile.exists() and modelfile.read_text()!=text:
        raise RuntimeError("Modelfile esistente differente: nessuna sovrascrittura")
    modelfile.write_text(text)
    env={**os.environ,"OLLAMA_HOST":"127.0.0.1:18499","OLLAMA_MODELS":str(STORE)}
    subprocess.run([executable,"create",manifest["model_alias"],"-f",str(modelfile)],env=env,check=True)
    subprocess.run([executable,"show",manifest["model_alias"]],env=env,check=True)
    print("Registrazione completata. Mantieni aperto il terminale del server MiniCPM.")


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download-models",action="store_true",help="Autorizza esplicitamente il download dei tre pesi (2.04 GB)")
    parser.add_argument("--register",action="store_true",help="Registra i pesi verificati nel server isolato già avviato")
    args=parser.parse_args(argv)
    manifest=json.loads(MANIFEST.read_text())
    if not args.download_models and not args.register:
        plan={**manifest,"total_download_bytes":sum(e["size"] for e in manifest["files"]),
              "weights_directory":str(WEIGHTS),"isolated_store":str(STORE),
              "downloads_started":False,"system_installation":False,
              "steps":["python scripts/setup_minicpm.py --download-models",
                       "python scripts/serve_minicpm.py (lasciare aperto)",
                       "python scripts/setup_minicpm.py --register",
                       "pdf2docx-ai doctor --json; verificare inferenza su fixture sintetica"]}
        print(json.dumps(plan,ensure_ascii=False,indent=2))
        return 0
    if args.download_models:
        import httpx
        WEIGHTS.mkdir(parents=True,exist_ok=True)
        if shutil.disk_usage(WEIGHTS).free<6_000_000_000:
            raise RuntimeError("Servono almeno 6 GB liberi per pesi e import Ollama")
        with httpx.Client(follow_redirects=True,trust_env=False,timeout=httpx.Timeout(120,connect=20)) as client:
            for entry in manifest["files"]: download(client,entry)
    if args.register: register(manifest)
    return 0


if __name__=="__main__":
    try: sys.exit(main())
    except (RuntimeError,OSError,subprocess.SubprocessError) as exc:
        print("Errore:",exc,file=sys.stderr);sys.exit(1)
