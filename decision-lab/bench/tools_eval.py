"""Avalia o ciclo decisão -> ferramenta em data/tools_eval.jsonl (75 falas, separadas do teste congelado).

  .venv/bin/python -m bench.tools_eval --selectors rules,model,hybrid                     # rota-ouro: isola o adaptador
  .venv/bin/python -m bench.tools_eval --selectors rules --router cascade-e5-decider-gguf  # ponta a ponta

Rota-ouro: a intenção correta é dada; mede só a escolha da ferramenta, a extração de parâmetros e as travas.
Ponta a ponta: o roteador real decide primeiro; os erros dele (ativar sem ser chamado, intenção errada) entram.
As ferramentas rodam de verdade, num contexto descartável (casa simulada nova, anotações em diretório temporário).
Resultados em runs/tools/ (TOOLS_DIR troca o diretório).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench.metrics import percentile  # noqa: E402
from lab import backends as registry  # noqa: E402
from lab.actions import ActionEngine, Planner  # noqa: E402
from lab.executors import Home  # noqa: E402
from lab.router import Policy, route_decision  # noqa: E402
from lab.taxonomy import ROOT, Taxonomy  # noqa: E402
from lab.tools.builtin import ToolContext, build_registry, norm  # noqa: E402

OUT = ROOT / os.environ.get("TOOLS_DIR", "runs/tools")
ACTED = {"executed", "answering"}


def load(name: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (ROOT / "data" / name).read_text(encoding="utf-8").splitlines() if line.strip()]


def same(a: Any, b: Any) -> bool:
    if isinstance(a, str) and isinstance(b, str):
        return norm(a).strip(" .,!?") == norm(b).strip(" .,!?")
    return a == b


def args_ok(gold: dict[str, Any] | None, got: dict[str, Any]) -> bool | None:
    if not gold:
        return None
    return all(k in got and same(v, got[k]) for k, v in gold.items())


def run(rows: list[dict[str, Any]], selector: str, router_name: str | None, selector_backend: str,
        config: dict[str, Any], scope: str = "route") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    taxonomy = Taxonomy.load()
    tools = build_registry()
    backend = registry.create(selector_backend, config) if selector != "rules" else None
    ctx = ToolContext(home=Home(), notes_path=Path(tempfile.mkdtemp()) / "notes.jsonl")
    engine = ActionEngine(tools, Planner(tools, selector, backend, scope=scope), ctx, set(taxonomy.keys), llm=lambda t, large, rid: None)
    router = registry.create(router_name, config) if router_name else None
    if router:
        options, question = taxonomy.options(router.option_lang), taxonomy.question(router.option_lang)
        for _ in range(3):
            router.warmup(options, question)
    if backend:  # o cache de schema só fica pronto na 2ª vez: aquece um schema por rota
        for route in ("LLM", "MEDIA", "TIMERS"):
            for _ in range(2):
                engine.planner.select("Alexa, que horas são?", route)
    preds = []
    for i, row in enumerate(rows):
        client = f"eval-{i}"  # um cliente por fala: uma pendência de confirmação não vaza para a fala seguinte
        if router:
            decision = router.decide(row["text"], options, question)
            predicted, route, decide_ms = decision.decision, route_decision(decision, taxonomy, Policy()).route, decision.latency_ms
        else:
            predicted, route, decide_ms = row["decision"], taxonomy.route(row["decision"]), 0.0
        start = time.perf_counter()
        out = engine.act(row["text"], predicted, route, client, f"eval-{i}")
        act_ms = (time.perf_counter() - start) * 1000
        gold_args = args_ok(row.get("args"), out["args"])
        preds.append({**row, "predicted_decision": predicted, "route": route, "got_tool": out["name"], "got_args": out["args"],
                      "got_status": out["status"], "say": out.get("say"), "selection": out.get("selection"),
                      "errors": out.get("errors"), "decide_ms": decide_ms, "act_ms": act_ms,
                      "tool_ok": out["name"] == row["tool"], "status_ok": out["status"] == row["status"], "args_ok": gold_args,
                      "ok": out["name"] == row["tool"] and out["status"] == row["status"] and gold_args is not False})
    engine.ctx.timers and [h.cancel() for h in engine.ctx.timers.values()]

    addressed = [p for p in preds if p["tool"] is not None]
    not_addressed = [p for p in preds if p["tool"] is None]
    with_args = [p for p in preds if p["args_ok"] is not None and p["tool_ok"]]
    multi = [p for p in addressed if len(tools.for_route(taxonomy.route(p["decision"]))) > 1]
    sensitive = [p for p in preds if "sensitive" in p["tags"]]
    select_ms = [p["selection"]["ms"] for p in preds if p.get("selection") and p["selection"]["method"].startswith("model")]
    summary = {
        "selector": selector, "scope": scope, "router": router_name or "rota-ouro", "n": len(preds),
        "outcome_accuracy": sum(p["ok"] for p in preds) / len(preds),
        "tool_accuracy_addressed": sum(p["tool_ok"] for p in addressed) / len(addressed),
        "tool_accuracy_multi_tool_routes": sum(p["tool_ok"] for p in multi) / len(multi), "n_multi": len(multi),
        "args_accuracy_when_tool_ok": (sum(p["args_ok"] for p in with_args) / len(with_args)) if with_args else None,
        "n_with_args": len(with_args),
        "status_accuracy": sum(p["status_ok"] for p in preds) / len(preds),
        # segurança
        "acted_when_not_addressed": sum(p["got_status"] in ACTED for p in not_addressed), "n_not_addressed": len(not_addressed),
        "asked_confirmation_when_not_addressed": sum(p["got_status"] == "needs_confirmation" for p in not_addressed),
        "sensitive_executed_without_confirmation": sum(p["got_status"] == "executed" and p["status"] == "needs_confirmation"
                                                       for p in sensitive),
        "n_sensitive": len(sensitive),
        "router_accuracy": (sum(p["predicted_decision"] == p["decision"] for p in preds) / len(preds)) if router else None,
        "decide_ms_p50": percentile([p["decide_ms"] for p in preds], 0.5) if router else None,
        "act_ms_p50": percentile([p["act_ms"] for p in preds if p["got_status"] != "ignored"] or [0.0], 0.5),
        "selection_ms_p50": percentile(select_ms, 0.5) if select_ms else None, "n_model_selections": len(select_ms),
        "by_tag": {tag: {"n": len(g), "ok": sum(p["ok"] for p in g) / len(g)}
                   for tag in sorted({t for p in preds for t in p["tags"]})
                   for g in [[p for p in preds if tag in p["tags"]]]},
        "errors": [{"text": p["text"], "gold": [p["tool"], p["status"]], "got": [p["got_tool"], p["got_status"]],
                    "args": p["got_args"], "why": p["errors"]} for p in preds if not p["ok"]],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    return preds, summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selectors", default="rules")
    parser.add_argument("--router", default=None, help="backend do roteador para o modo ponta a ponta (padrão: rota-ouro)")
    parser.add_argument("--selector-backend", default=None)
    parser.add_argument("--scope", default="route", choices=["route", "all"])
    args = parser.parse_args()
    config = registry.load_config()
    rows = load("tools_eval.jsonl")
    frozen = {norm(r["text"]) for name in ("test.jsonl", "train.jsonl") for r in load(name)}
    leaked = [r["text"] for r in rows if norm(r["text"]) in frozen]
    if leaked:
        raise SystemExit(f"falas da avaliação de ferramentas repetem o dataset congelado: {leaked}")
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "summary.json"
    results = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    selector_backend = args.selector_backend or config.get("tools", {}).get("selector_backend", "decider-0.8b-gguf-restore")
    for selector in args.selectors.split(","):
        key = f"{args.router or 'gold'}+{selector}" + ("" if args.scope == "route" else f"+{args.scope}")
        preds, summary = run(rows, selector, args.router, selector_backend, config, args.scope)
        results[key] = summary
        (OUT / f"predictions-{key}.jsonl").write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in preds), encoding="utf-8")
        path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        f = lambda v: "-" if v is None else f"{v:.3f}"  # noqa: E731
        print(f"{key:40s} desfecho={f(summary['outcome_accuracy'])} ferramenta={f(summary['tool_accuracy_addressed'])} "
              f"(rotas com escolha: {f(summary['tool_accuracy_multi_tool_routes'])}) args={f(summary['args_accuracy_when_tool_ok'])} "
              f"agiu_sem_ser_chamado={summary['acted_when_not_addressed']}/{summary['n_not_addressed']} "
              f"sensível_sem_confirmar={summary['sensitive_executed_without_confirmation']} "
              f"seleção_p50={f(summary['selection_ms_p50'])}ms", flush=True)
        for e in summary["errors"]:
            print(f"   ✗ {e['text']!r}: esperado {e['gold']}, veio {e['got']} {e['args'] or ''} {e['why'] or ''}")


if __name__ == "__main__":
    main()
