"""Cascatas simuladas a partir das predições salvas (sem rodar modelos de novo).

  .venv/bin/python -m bench.cascade --first e5-logreg --second jeff-0.8b,qwen3.5-4b-chat

Estágio 1 (barato) decide sozinho quando confiança >= τ; abaixo disso a fala vai para o estágio 2 (caro).
Latência esperada = lat1 + fração_escalada * lat2. Mostra o quanto a confiança do estágio 1 é útil como
sinal de roteamento: se ela não separa acertos de erros, escalar não melhora nada.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench.metrics import binary_metrics, correct  # noqa: E402
from lab.taxonomy import ROOT  # noqa: E402

BENCH = ROOT / "runs" / "bench"


def load(name: str) -> list[dict]:
    return [json.loads(line) for line in (BENCH / name / "predictions.jsonl").read_text().splitlines()]


def simulate(first: list[dict], second: list[dict], tau: float) -> dict:
    merged, escalated = [], 0
    for a, b in zip(first, second, strict=True):
        if a["confidence"] is not None and a["confidence"] >= tau:
            merged.append(a)
        else:
            merged.append(b)
            escalated += 1
    lat = [a["latency_ms"] + (b["latency_ms"] if not (a["confidence"] is not None and a["confidence"] >= tau) else 0)
           for a, b in zip(first, second)]
    return {"tau": tau, "accuracy": sum(map(correct, merged)) / len(merged), **binary_metrics(merged),
            "escalated": escalated / len(merged), "mean_latency_ms": statistics.fmean(lat)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--first", required=True)
    parser.add_argument("--second", required=True)
    parser.add_argument("--taus", default="0,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1.01")
    args = parser.parse_args()
    first = load(args.first)
    out = {}
    for second_name in args.second.split(","):
        second = load(second_name)
        key = f"{args.first} -> {second_name}"
        out[key] = [simulate(first, second, float(t)) for t in args.taus.split(",")]
        print(f"\n### {key}\n")
        print("| τ | escalado | acurácia | falsa ativação | perdidos | latência média |")
        print("|---|---|---|---|---|---|")
        for r in out[key]:
            print(f"| {r['tau']:.2f} | {r['escalated'] * 100:.0f}% | {r['accuracy'] * 100:.1f}% "
                  f"| {r['false_activation_rate'] * 100:.1f}% | {r['missed_rate'] * 100:.1f}% | {r['mean_latency_ms']:.0f} ms |")
    path = BENCH / "cascades.json"
    existing = json.loads(path.read_text()) if path.exists() else {}
    existing.update(out)
    path.write_text(json.dumps(existing, indent=2))


if __name__ == "__main__":
    main()
