#!/usr/bin/env bash
# Inicia/para os servidores de modelos usados pelo laboratório.
#   scripts/services.sh start [grupo...]   grupos: jeff decider decider-gguf decision llm-small llm-large all (padrão: all)
#   scripts/services.sh stop [grupo...]    sem grupo: para tudo
#   scripts/services.sh status
# "all" precisa de ~15 GB de RAM; em máquinas menores suba só os grupos que o benchmark usa.
set -euo pipefail
cd "$(dirname "$0")/.."
LAB=$PWD
LOGS=$LAB/runs/logs
mkdir -p "$LOGS"
LLAMA=$LAB/vendor/llama.cpp/build/bin/llama-server
THREADS=${THREADS:-$(nproc)}   # llama.cpp; em desktop com outras cargas use nproc-2 (oversubscription derruba a geração)
# TORCH_THREADS limita os servidores PyTorch (Jeff, decider); sem ela, o padrão do torch.
[ -n "${TORCH_THREADS:-}" ] && export OMP_NUM_THREADS=$TORCH_THREADS MKL_NUM_THREADS=$TORCH_THREADS

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
  [ -x "$LLAMA" ] || { echo "  llama-server não encontrado em $LLAMA (rode scripts/setup.sh nesta pasta)"; exit 1; }
  [ -f "$LAB/models/gguf/$model" ] || { echo "  modelo não encontrado: models/gguf/$model"; exit 1; }
  echo "  subindo $name em :$port ..."
  nohup "$LLAMA" -m "$LAB/models/gguf/$model" --port "$port" -t "$THREADS" --no-webui --cache-ram 0 "$@" > "$LOGS/$name.log" 2>&1 &
  wait_for "$port" ok
}

start_jeff() {
  if curl -s localhost:8765/health >/dev/null 2>&1; then echo "  :8765 já rodando (jeff)"; return; fi
  (cd vendor/jeff && JEFF_CHECKPOINT=$LAB/models/Jeff-Qwen3.5-0.8B-v1.2 PORT=8765 \
    nohup .venv/bin/jeff-serve > "$LOGS/jeff.log" 2>&1 &)
  wait_for 8765 ready
}

start_decider() {  # cache de schema: opções primeiro, prefixo calculado uma vez (fp32 na CPU por padrão)
  if curl -s localhost:8821/health >/dev/null 2>&1; then echo "  :8821 já rodando (decider)"; return; fi
  (cd vendor/decider && DECIDER_MODEL=$LAB/models/decider-0.8b DECIDER_SCHEMA_CACHE=1 \
    nohup .venv/bin/uvicorn decider.serve:app --host 127.0.0.1 --port 8821 > "$LOGS/decider.log" 2>&1 &)
  wait_for 8821 .
}

start() {
  local groups=("${@:-all}")
  for g in "${groups[@]}"; do
    case $g in
      jeff) start_jeff ;;
      decider) start_decider ;;
      decider-gguf) SLOT_DIR=${SLOT_DIR:-$LAB/runs/slots}; mkdir -p "$SLOT_DIR"   # no WSL, use um caminho fora de /mnt/c
                    llama decider-gguf 8822 decider-0.8b-Q8_0.gguf -c 4096 -np 1 --slot-save-path "$SLOT_DIR" ${DECIDER_GGUF_ARGS:-} ;;
      decision) llama julia 8811 Julia-1-Q8_0.gguf; llama laya 8812 Laya-Q8_0.gguf ;;
      llm-small) llama qwen08 8801 Qwen3.5-0.8B-Q8_0.gguf -c 4096 -np 1 ;;
      llm-large) llama qwen2b 8802 Qwen3.5-2B-Q4_K_M.gguf -c 4096 -np 1
                 llama qwen4b 8803 Qwen3.5-4B-Q4_K_M.gguf -c 4096 -np 1 ;;
      all) start_jeff; start_decider; start decision llm-small llm-large ;;
      *) echo "grupo desconhecido: $g"; exit 1 ;;
    esac
  done
}

stop_port() { for p in "$@"; do fuser -k "$p/tcp" >/dev/null 2>&1 || true; done; }

stop() {
  if [ $# -eq 0 ]; then
    pkill -f "$LLAMA" || true; pkill -f jeff-serve || true; pkill -f "decider[.]serve" || true
  else
    for g in "$@"; do
      case $g in
        jeff) stop_port 8765 ;;
        decider) stop_port 8821 ;;
        decider-gguf) stop_port 8822 ;;
        decision) stop_port 8811 8812 ;;
        llm-small) stop_port 8801 ;;
        llm-large) stop_port 8802 8803 ;;
        *) echo "grupo desconhecido: $g"; exit 1 ;;
      esac
    done
  fi
  echo "parado"
}

case ${1:-status} in
  start) shift; start "$@" ;;
  stop) shift; stop "$@" ;;
  status) for p in 8765 8821 8822 8811 8812 8801 8802 8803; do printf ":%s %s\n" "$p" "$(curl -s -m 2 localhost:$p/health || echo '-')"; done ;;
  *) echo "uso: $0 start|stop|status"; exit 1 ;;
esac
