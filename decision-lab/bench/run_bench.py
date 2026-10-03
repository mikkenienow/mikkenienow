"""Benchmark do router sobre data/test.jsonl.

  .venv/bin/python -m bench.run_bench --backends jeff-0.8b,julia-1,tfidf-logreg [--perturb] [--limit N]

Para cada backend: aquece, decide cada item em sequência (uma requisição por vez, como num fluxo de
voz), mede latência de parede e CPU consumida (processo do laboratório + processo do servidor do
modelo, achado pela porta) e salva predições + resumo em runs/bench/<backend>/.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench.metrics import summarize  # noqa: E402
from lab import backends as registry  # noqa: E402
from lab.taxonomy import ROOT, Taxonomy  # noqa: E402

OUT = ROOT / "runs" / "bench"


def load_test(limit: int | None = None) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in (ROOT / "data" / "test.jsonl").read_text().splitlines()]
    return rows[::max(1, len(rows) // limit)][:limit] if limit else rows  # amostra espalhada


def perturb(text: str) -> str:
    """Simula a saída "crua" de um STT: minúsculas, sem acentos, sem pontuação."""
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", t)).strip()


def server_process(port: int | None) -> psutil.Process | None:
    if not port:
        return None
    for conn in psutil.net_connections(kind="tcp"):
        if conn.laddr and conn.laddr.port == port and conn.status == psutil.CONN_LISTEN and conn.pid:
            return psutil.Process(conn.pid)
    return None


def cpu_seconds(procs: list[psutil.Process]) -> float:
    total = 0.0
    for p in procs:
        t = p.cpu_times()
        total += t.user + t.system
    return total


def run_pass(backend: Any, rows: list[dict[str, Any]], options: Any, question: str,
             transform: Any = None, label: str = "") -> list[dict[str, Any]]:
    out = []
    for i, row in enumerate(rows):
        text = transform(row["text"]) if transform else row["text"]
        d = backend.decide(text, options, question)
        out.append({**row, "input": text, "decision": d.decision, "confidence": d.confidence, "scores": d.scores,
                    "score_kind": d.score_kind, "latency_ms": d.latency_ms, "metadata": d.metadata})
        if (i + 1) % 20 == 0:
            print(f"    {label}{i + 1}/{len(rows)}", flush=True)
    return out


def bench_backend(name: str, rows: list[dict[str, Any]], do_perturb: bool, config: dict[str, Any]) -> dict[str, Any]:
    taxonomy = Taxonomy.load()
    me = psutil.Process()
    rss_before = me.memory_info().rss
    t0 = time.perf_counter()
    backend = registry.create(name, config)
    load_s = time.perf_counter() - t0
    options, question = taxonomy.options(backend.option_lang), taxonomy.question(backend.option_lang)
    for _ in range(2):
        backend.warmup(options, question)
    server = server_process(backend.port)
    procs = [me] + ([server] if server else [])
    cpu0, wall0 = cpu_seconds(procs), time.perf_counter()
    preds = run_pass(backend, rows, options, question)
    cpu1, wall1 = cpu_seconds(procs), time.perf_counter()
    perturbed = run_pass(backend, rows, options, question, perturb, "perturb ") if do_perturb else None
    summary = summarize(preds, perturbed)
    summary.update({
        "backend": name, "kind": backend.kind, "model": backend.model, "option_lang": backend.option_lang,
        "load_seconds": load_s,
        "cpu_seconds_per_decision": (cpu1 - cpu0) / len(rows),
        "wall_seconds_per_decision": (wall1 - wall0) / len(rows),
        "cpu_cores_busy": (cpu1 - cpu0) / (wall1 - wall0),
        "rss_mb": {"server": round(server.memory_info().rss / 2**20) if server else None,
                   "lab_process_delta": round((me.memory_info().rss - rss_before) / 2**20)},
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    folder = OUT / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "predictions.jsonl").write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in preds))
    if perturbed:
        (folder / "predictions_perturbed.jsonl").write_text(
            "".join(json.dumps(p, ensure_ascii=False) + "\n" for p in perturbed))
    (folder / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backends", required=True, help="nomes separados por vírgula (config/backends.yaml)")
    parser.add_argument("--perturb", action="store_true", help="2ª passada com texto normalizado (estabilidade)")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    config = registry.load_config()
    rows = load_test(args.limit)
    for name in args.backends.split(","):
        print(f"== {name}", flush=True)
        try:
            s = bench_backend(name, rows, args.perturb, config)
        except Exception as error:  # um backend quebrado não derruba a bateria
            print(f"   FALHOU: {error!r}", flush=True)
            continue
        f = lambda v: "-" if v is None else f"{v:.3f}"  # noqa: E731
        print(f"   acc={f(s['accuracy'])} falsa_ativação={f(s['false_activation_rate'])} "
              f"perdidos={f(s['missed_rate'])} p50={s['latency_ms']['p50']:.0f}ms "
              f"cpu/decisão={s['cpu_seconds_per_decision']:.2f}s ece={f(s['ece'])}", flush=True)


if __name__ == "__main__":
    main()
