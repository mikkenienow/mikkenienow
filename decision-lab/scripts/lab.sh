#!/usr/bin/env bash
# Sobe a API/UI do laboratório em http://127.0.0.1:${PORT:-8000}
#   HOST=0.0.0.0 scripts/lab.sh   # para acessar de outro dispositivo da rede (ex.: celular, Fase 3)
set -euo pipefail
cd "$(dirname "$0")/.."
# LAB_BACKEND=<nome> troca o backend padrão; LAB_PRELOAD=0 desliga a pré-carga do modelo ao subir
exec .venv/bin/uvicorn lab.server:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}"
