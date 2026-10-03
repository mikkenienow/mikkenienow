"""Métricas de avaliação de um router de decisão."""

from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any

IGNORE = "ignore"
LLM_KEYS = {"knowledge", "complex"}
PROB_KINDS = {"probability", "pseudo_probability", "token_probability"}


def percentile(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    k = (len(s) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def correct(row: dict[str, Any]) -> bool:
    return row["decision"] in row["accept"]


def addressed_truth(row: dict[str, Any]) -> bool | None:
    """True: certamente destinada ao assistente; False: certamente não; None: ambígua (fora da métrica)."""
    accept = set(row["accept"])
    if accept == {IGNORE}:
        return False
    if IGNORE not in accept:
        return True
    return None


def ece(rows: list[dict[str, Any]], bins: int = 10) -> float | None:
    pairs = [(r["confidence"], correct(r)) for r in rows if r.get("confidence") is not None]
    if not pairs:
        return None
    total, err = len(pairs), 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        bucket = [(c, ok) for c, ok in pairs if lo <= c < hi or (b == bins - 1 and c == 1.0)]
        if bucket:
            conf = sum(c for c, _ in bucket) / len(bucket)
            acc = sum(ok for _, ok in bucket) / len(bucket)
            err += len(bucket) / total * abs(conf - acc)
    return err


def auroc(rows: list[dict[str, Any]]) -> float | None:
    """A confiança separa acertos de erros? 0.5 = não ajuda; 1.0 = separa perfeitamente."""
    pos = [r["confidence"] for r in rows if r.get("confidence") is not None and correct(r)]
    neg = [r["confidence"] for r in rows if r.get("confidence") is not None and not correct(r)]
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def threshold_sweep(rows: list[dict[str, Any]], thresholds: list[float]) -> list[dict[str, Any]]:
    """Política 'baixa confiança -> ignorar'. Mede o efeito do limiar sobre ativações e acertos."""
    out = []
    for tau in thresholds:
        sim = []
        for r in rows:
            d = r["decision"]
            if d != IGNORE and r.get("confidence") is not None and r["confidence"] < tau:
                d = IGNORE
            sim.append({**r, "decision": d})
        m = binary_metrics(sim)
        out.append({"threshold": tau, "accuracy": sum(map(correct, sim)) / len(sim),
                    "false_activation_rate": m["false_activation_rate"], "missed_rate": m["missed_rate"]})
    return out


def binary_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    neg = [r for r in rows if addressed_truth(r) is False]
    pos = [r for r in rows if addressed_truth(r) is True]
    fa = sum(r["decision"] != IGNORE for r in neg)
    missed = sum(r["decision"] == IGNORE for r in pos)
    return {"negatives": len(neg), "positives": len(pos),
            "false_activation_rate": fa / len(neg) if neg else None,  # falso positivo: acordou sem ser chamado
            "missed_rate": missed / len(pos) if pos else None}  # falso negativo: ignorou um pedido


def llm_economics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    need = [r for r in rows if r["label"] in LLM_KEYS]
    called = [r for r in rows if r["decision"] in LLM_KEYS]
    missed = sum(r["decision"] not in LLM_KEYS for r in need)
    wasted = sum(r["label"] not in LLM_KEYS and not (set(r["accept"]) & LLM_KEYS) for r in called)
    return {"llm_calls": len(called), "llm_calls_if_no_router": n, "calls_avoided_pct": 1 - len(called) / n,
            "llm_needed": len(need), "llm_missed": missed, "llm_wasted": wasted}


def summarize(rows: list[dict[str, Any]], perturbed: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    lat = [r["latency_ms"] for r in rows]
    by_tag: dict[str, list[bool]] = defaultdict(list)
    by_label: dict[str, list[bool]] = defaultdict(list)
    for r in rows:
        for tag in r["tags"]:
            by_tag[tag].append(correct(r))
        by_label[r["label"]].append(correct(r))
    kinds = {r.get("score_kind") for r in rows}
    calibrated = bool(kinds & PROB_KINDS)
    intent_rows = [r for r in rows if addressed_truth(r) is True and r["decision"] != IGNORE]
    summary: dict[str, Any] = {
        "n": len(rows),
        "accuracy": sum(map(correct, rows)) / len(rows),
        "accuracy_strict": sum(r["decision"] == r["label"] for r in rows) / len(rows),
        "intent_accuracy_when_addressed": (sum(map(correct, intent_rows)) / len(intent_rows)) if intent_rows else None,
        **binary_metrics(rows),
        "latency_ms": {"mean": statistics.fmean(lat), "p50": percentile(lat, 0.5), "p95": percentile(lat, 0.95),
                       "max": max(lat)},
        "score_kind": sorted(k for k in kinds if k),
        "ece": ece(rows) if calibrated else None,
        "auroc_confidence": auroc(rows),
        "by_tag": {t: {"n": len(v), "accuracy": sum(v) / len(v)} for t, v in sorted(by_tag.items())},
        "by_label": {t: {"n": len(v), "accuracy": sum(v) / len(v)} for t, v in sorted(by_label.items())},
        "llm": llm_economics(rows),
    }
    confs = sorted({round(r["confidence"], 2) for r in rows if r.get("confidence") is not None})
    if confs:
        grid = [0.0, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95] if calibrated else \
            [round(percentile(confs, q), 3) for q in (0, .1, .2, .3, .4, .5, .6, .7, .8, .9)]
        summary["threshold_sweep"] = threshold_sweep(rows, grid)
    if perturbed:
        same = sum(a["decision"] == b["decision"] for a, b in zip(rows, perturbed))
        summary["perturbation_agreement"] = same / len(rows)
        summary["accuracy_perturbed"] = sum(map(correct, perturbed)) / len(perturbed)
    return summary
