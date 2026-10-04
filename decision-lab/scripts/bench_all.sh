#!/usr/bin/env bash
# Bateria de re-medição em uma máquina nova: um backend por vez, só o serviço necessário no ar.
#   BENCH_DIR=runs/bench-local THREADS=4 scripts/bench_all.sh [etapa...]
# Etapas (padrão: todas, nesta ordem): main scaling pipeline cascade report
set -uo pipefail
cd "$(dirname "$0")/.."
export BENCH_DIR=${BENCH_DIR:-runs/bench-local}
PY=.venv/bin/python
S=scripts/services.sh

only() {  # para tudo e sobe só os grupos pedidos
  $S stop >/dev/null 2>&1; pkill -f "[u]vicorn lab.server" 2>/dev/null; sleep 3
  [ $# -eq 0 ] || $S start "$@"
}

main() {
  only;           $PY -m bench.run_bench --backends e5-logreg --perturb
  only decider;   $PY -m bench.run_bench --backends decider-0.8b-schema --perturb
  only jeff;      $PY -m bench.run_bench --backends jeff-0.8b --perturb
                  $PY -m bench.run_bench --backends jeff-0.8b-pt --perturb
  only llm-small; $PY -m bench.run_bench --backends qwen3.5-0.8b-logprob --perturb
  only llm-large; $PY -m bench.run_bench --backends qwen3.5-4b-chat --perturb
}

scaling() {
  only decider; $PY -m bench.scaling --backends decider-0.8b-schema
  only jeff;    $PY -m bench.scaling --backends jeff-0.8b
}

pipeline() {
  only decider llm-large
  nohup scripts/lab.sh > runs/logs/lab.log 2>&1 &
  for _ in $(seq 1 120); do curl -s localhost:8000/v1/backends >/dev/null 2>&1 && break; sleep 1; done
  $PY -m bench.pipeline --baseline --routers cascade-e5-decider,decider-0.8b-schema,qwen3.5-4b-chat
}

cascade() {
  $PY -m bench.cascade --first e5-logreg --second decider-0.8b-schema,jeff-0.8b,jeff-0.8b-pt,qwen3.5-4b-chat
}

report() { $PY -m bench.report > "$BENCH_DIR/REPORT.md"; echo "relatório em $BENCH_DIR/REPORT.md"; }

for step in "${@:-main scaling pipeline cascade report}"; do
  for s in $step; do echo "##### $s $(date +%H:%M:%S)"; $s; done
done
only
echo "##### FIM $(date +%H:%M:%S)"
