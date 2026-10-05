"""Benchmarks do laboratório.

O diretório de resultados é parametrizável para comparar máquinas sem sobrescrever medições:
  BENCH_DIR=runs/bench-local .venv/bin/python -m bench.run_bench ...
(relativo à raiz do laboratório, ou absoluto; padrão: runs/bench).
"""

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def bench_dir() -> Path:
    path = _ROOT / os.environ.get("BENCH_DIR", "runs/bench")  # caminho absoluto substitui a raiz
    path.mkdir(parents=True, exist_ok=True)
    return path
