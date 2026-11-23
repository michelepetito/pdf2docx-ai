"""Run repository-local Ollama on port 18499; no downloads or system services."""
from pathlib import Path
import argparse
import os
import shutil
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / 'models' / 'ollama'


def main(argv=None):
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    executable = shutil.which('ollama')
    if not executable:
        raise RuntimeError('Install Ollama first and make the ollama command available in PATH.')
    with socket.socket() as check:
        try:
            check.bind(('127.0.0.1', 18499))
        except OSError as exc:
            raise RuntimeError('Port 18499 is occupied. The existing server is left unchanged.') from exc
    STORE.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, 'OLLAMA_HOST': '127.0.0.1:18499', 'OLLAMA_MODELS': str(STORE),
           'OLLAMA_NUM_PARALLEL': '1', 'OLLAMA_MAX_LOADED_MODELS': '1'}
    process = subprocess.Popen([executable, 'serve'], env=env)
    pid_file = STORE / 'server.pid'
    try:
        pid_file.write_text(str(process.pid), encoding='utf-8')
        print('MiniCPM: http://127.0.0.1:18499 — Ctrl-C to stop this server.', flush=True)
        try:
            return process.wait()
        except KeyboardInterrupt:
            return 0
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        if pid_file.is_file() and pid_file.read_text(encoding='utf-8').strip() == str(process.pid):
            pid_file.unlink()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
