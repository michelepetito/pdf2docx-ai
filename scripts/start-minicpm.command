#!/bin/zsh
set -eu
cd "$(dirname "$0")/.."
if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama non presente. Questo script non installa componenti di sistema."
  exit 1
fi
if lsof -nP -iTCP:18499 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Porta 18499 già occupata. Non modifico il server esistente."
  exit 1
fi
mkdir -p models/ollama
chmod 700 models models/ollama
export OLLAMA_HOST=127.0.0.1:18499
export OLLAMA_MODELS="$PWD/models/ollama"
export OLLAMA_NUM_PARALLEL=1
export OLLAMA_MAX_LOADED_MODELS=1
echo $$ > models/ollama/server.pid
echo "MiniCPM locale: http://127.0.0.1:18499 — Ctrl-C per arrestare."
exec ollama serve
