#!/bin/zsh
set -eu
cd "$(dirname "$0")/.."
if [ ! -f models/ollama/server.pid ]; then
  echo "Nessun PID del server MiniCPM nel repository."
  exit 1
fi
minicpm_pid="$(cat models/ollama/server.pid)"
if [[ "$minicpm_pid" != <1-> ]]; then
  echo "PID non valido: nessun processo arrestato."
  exit 1
fi
minicpm_listener="$(lsof -nP -t -iTCP:18499 -sTCP:LISTEN || true)"
if [ "$minicpm_listener" != "$minicpm_pid" ]; then
  echo "Il PID non corrisponde al listener 18499: nessun processo arrestato."
  exit 1
fi
kill -TERM "$minicpm_pid"
echo "Richiesto arresto del solo server MiniCPM sulla porta 18499."
