#!/bin/zsh
set -eu
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/pdf2docx-ai ]; then
  echo "Installare prima il progetto seguendo README.md"
  exit 1
fi
exec .venv/bin/pdf2docx-ai serve
