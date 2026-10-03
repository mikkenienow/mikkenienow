"""Fase 2: o modelo de decisão como "porteiro" na frente de LLMs, medido ponta a ponta pela API real.

  scripts/lab.sh &   # servidor do laboratório em :8000
  .venv/bin/python -m bench.pipeline --routers julia-1,jeff-0.8b,qwen3.5-4b-chat --limit 80 [--baseline]

Para cada router, cada fala do fluxo vai para POST /v1/route (wait_llm=true): decisão -> rota -> executor
(casa simulada) ou LLM local (Qwen3.5-2B para LLM, 4B para LLM_LARGE), e medimos o tempo total de cada fala.
--baseline: o fluxo SEM porteiro — toda fala vai direto ao LLM (2B), como um assistente que manda tudo ao modelo.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench.metrics import LLM_KEYS, binary_metrics, correct  # noqa: E402
from bench.run_bench import load_test  # noqa: E402
from lab import backends as registry  # noqa: E402
from lab.executors import LlmExecutor  # noqa: E402
from lab.taxonomy import ROOT  # noqa: E402

API = "http://127.0.0.1:8000"


def stream(limit: int | None) -> list[dict[str, Any]]:
    rows = load_test(limit)
    random.Random(7).shuffle(rows)
    return rows


def run_router(router: str, rows: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    client = httpx.Client(timeout=900)
    preds, e2e = [], []
    for i, row in enumerate(rows):
        start = time.perf_counter()
        r = client.post(f"{API}/v1/route", json={"input": row["text"], "backend": router, "min_confidence": threshold,
                                                   "wait_llm": True, "source": f"pipeline:{router}"}).json()
        e2e.append((time.perf_counter() - start) * 1000)
        preds.append({**row, "decision": r["decision"] if r["route"] != "NONE" else "ignore", "route": r["route"],
                      "decision_ms": r["latency_ms"], "e2e_ms": e2e[-1], "confidence": r["confidence"]})
        if (i + 1) % 20 == 0:
            print(f"   {router} {i + 1}/{len(rows)}", flush=True)
    llm = [p for p in preds if p["route"] in ("LLM", "LLM_LARGE")]
    return {
        "router": router, "threshold": threshold, "n": len(rows),
        "accuracy_after_policy": sum(map(correct, preds)) / len(preds), **binary_metrics(preds),
        "total_seconds": sum(e2e) / 1000,
        "decision_seconds": sum(p["decision_ms"] for p in preds) / 1000,
        "llm_seconds": sum(p["e2e_ms"] - p["decision_ms"] for p in llm) / 1000,
        "llm_calls": len(llm),
        "llm_calls_needed": sum(p["label"] in LLM_KEYS for p in preds),
        "llm_wasted": sum(not (set(p["accept"]) & LLM_KEYS) for p in llm),
        "llm_missed": sum(p["label"] in LLM_KEYS and p["route"] not in ("LLM", "LLM_LARGE") for p in preds),
        "mean_e2e_ms_by_route": {route: statistics.fmean([p["e2e_ms"] for p in preds if p["route"] == route])
                                 for route in sorted({p["route"] for p in preds})},
        "mean_decision_ms": statistics.fmean(p["decision_ms"] for p in preds),
    }


def run_baseline(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Sem porteiro: o LLM recebe tudo (e responde até conversa de fundo)."""
    config = registry.load_config()
    spec = config["backends"][config["llm_executor"]]
    executor = LlmExecutor(spec["url"], spec["model"])
    times, tokens = [], []
    for i, row in enumerate(rows):
        result = executor.answer(row["text"])
        times.append(result["llm_latency_ms"])
        tokens.append(result.get("completion_tokens") or 0)
        if (i + 1) % 20 == 0:
            print(f"   baseline {i + 1}/{len(rows)}", flush=True)
    return {"router": "none (tudo -> LLM 2B)", "n": len(rows), "total_seconds": sum(times) / 1000,
            "llm_calls": len(rows), "llm_calls_needed": sum(r["label"] in LLM_KEYS for r in rows),
            "llm_wasted": sum(r["label"] not in LLM_KEYS for r in rows),
            "false_activation_rate": 1.0, "mean_llm_ms": statistics.fmean(times),
            "mean_completion_tokens": statistics.fmean(tokens)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--routers", default="")
    parser.add_argument("--threshold", type=float, default=0.0)
    parser.add_argument("--limit", type=int, default=80)
    parser.add_argument("--baseline", action="store_true")
    args = parser.parse_args()
    rows = stream(args.limit)
    out_path = ROOT / "runs" / "bench" / "pipeline.json"
    results = json.loads(out_path.read_text()) if out_path.exists() else {}
    if args.baseline:
        results["baseline"] = run_baseline(rows)
        print(json.dumps(results["baseline"], indent=1), flush=True)
        out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    for router in filter(None, args.routers.split(",")):
        key = f"{router}@{args.threshold}"
        results[key] = run_router(router, rows, args.threshold)
        print(json.dumps(results[key], indent=1, ensure_ascii=False), flush=True)
        out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
