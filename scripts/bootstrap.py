"""Create a project-local environment on macOS, Linux or Windows."""
from pathlib import Path
import argparse
import struct
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dev', action='store_true', help='Also install test dependencies')
    parser.add_argument('--venv', type=Path, default=ROOT / '.venv', help='Environment directory')
    args = parser.parse_args(argv)
    if not (3, 11) <= sys.version_info[:2] < (3, 14):
        parser.error('Use Python 3.11–3.13 (recommended: Python 3.12).')
    if struct.calcsize('P') != 8:
        parser.error('Use a 64-bit Python matching your operating system architecture.')
    target = args.venv.resolve()
    python = target / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    if target.exists() and not python.is_file():
        parser.error(f'{target} exists without a compatible environment; choose a new --venv directory.')
    if not target.exists():
        venv.EnvBuilder(with_pip=True).create(target)
    subprocess.run([str(python), '-m', 'pip', 'install', '--upgrade', 'pip'], check=True)
    subprocess.run([str(python), '-m', 'pip', 'install', '-c', str(ROOT / 'constraints.txt'),
                    '-e', str(ROOT) + ('[test]' if args.dev else '')], cwd=ROOT, check=True)
    subprocess.run([str(python), '-m', 'pip', 'check'], check=True)
    print('\nEnvironment ready:', target)
    print('Run:', subprocess.list2cmdline([str(python), '-m', 'pdf2docx_ai', 'doctor', '--json']))
    print('Run:', subprocess.list2cmdline([str(python), '-m', 'pdf2docx_ai', 'serve']))
    print('Open http://127.0.0.1:8765 — LibreOffice, Tesseract and model weights are installed separately.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
