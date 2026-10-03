#!/usr/bin/env bash
# Inicia/para os servidores de modelos usados pelo laboratório.
#   scripts/services.sh start [grupo...]   grupos: jeff decision llm-small llm-large all (padrão: all)
#   scripts/services.sh stop
#   scripts/services.sh status
set -euo pipefail
cd "$(dirname "$0")/.."
LAB=$PWD
LOGS=$LAB/runs/logs
mkdir -p "$LOGS"
LLAMA=$LAB/vendor/llama.cpp/build/bin/llama-server
THREADS=${THREADS:-$(nproc)}

wait_for() {  # porta, padrão esperado no /health
  for _ in $(seq 1 180); do
    curl -s "localhost:$1/health" | grep -qE "$2" && { echo "  :$1 pronto"; return 0; }
    sleep 1
  done
  echo "  :$1 NÃO respondeu (veja $LOGS)"; return 1
}

llama() {  # nome porta modelo [args extras]
  local name=$1 port=$2 model=$3; shift 3
  if curl -s "localhost:$port/health" >/dev/null 2>&1; then echo "  :$port já rodando ($name)"; return; fi
  nohup "$LLAMA" -m "$LAB/models/gguf/$model" --port "$port" -t "$THREADS" --no-webui --cache-ram 0 "$@" > "$LOGS/$name.log" 2>&1 &
  wait_for "$port" ok
}

start_jeff() {
  if curl -s localhost:8765/health >/dev/null 2>&1; then echo "  :8765 já rodando (jeff)"; return; fi
  (cd vendor/jeff && JEFF_CHECKPOINT=$LAB/models/Jeff-Qwen3.5-0.8B-v1.2 PORT=8765 \
    nohup .venv/bin/jeff-serve > "$LOGS/jeff.log" 2>&1 &)
  wait_for 8765 ready
}

start() {
  local groups=("${@:-all}")
  for g in "${groups[@]}"; do
    case $g in
      jeff) start_jeff ;;
      decision) llama julia 8811 Julia-1-Q8_0.gguf; llama laya 8812 Laya-Q8_0.gguf ;;
      llm-small) llama qwen08 8801 Qwen3.5-0.8B-Q8_0.gguf -c 4096 -np 1 ;;
      llm-large) llama qwen2b 8802 Qwen3.5-2B-Q4_K_M.gguf -c 4096 -np 1
                 llama qwen4b 8803 Qwen3.5-4B-Q4_K_M.gguf -c 4096 -np 1 ;;
      all) start_jeff; start decision llm-small llm-large ;;
      *) echo "grupo desconhecido: $g"; exit 1 ;;
    esac
  done
}

case ${1:-status} in
  start) shift; start "$@" ;;
  stop) pkill -f "$LLAMA" || true; pkill -f jeff-serve || true; echo "parado" ;;
  status) for p in 8765 8811 8812 8801 8802 8803; do printf ":%s %s\n" "$p" "$(curl -s -m 2 localhost:$p/health || echo '-')"; done ;;
  *) echo "uso: $0 start|stop|status"; exit 1 ;;
esac
