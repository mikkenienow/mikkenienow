"""Gera tabelas markdown a partir de runs/bench/*/summary.json (e scaling.json / pipeline.json).

  .venv/bin/python -m bench.report > runs/bench/REPORT.md
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench import bench_dir  # noqa: E402

BENCH = bench_dir()
GROUP = {"decision-model": "C) decisão", "llm-logprob": "D) LLM genérico (logprob)",
         "llm-generative": "A) LLM generativo", "zero-shot-nli": "zero-shot", "zero-shot-gliclass": "zero-shot",
         "zero-shot-embedding": "zero-shot", "trained-tfidf": "B) treinado", "trained-embedding": "B) treinado",
         "trained-knn": "B) treinado"}


def f(v: float | None, pct: bool = False, digits: int = 3) -> str:
    if v is None:
        return "–"
    return f"{v * 100:.1f}%" if pct else f"{v:.{digits}f}"


def main() -> None:
    rows = [json.loads(p.read_text()) for p in sorted(BENCH.glob("*/summary.json"))]
    rows.sort(key=lambda r: (list(GROUP).index(r["kind"]) if r["kind"] in GROUP else 99, r["latency_ms"]["p50"]))
    print("## Resultado principal (159 falas, taxonomia de 6 classes)\n")
    print("| backend | grupo | acurácia | falsa ativação | pedidos perdidos | intenção (se ativado) | p50 | p95 | CPU-s/decisão | ECE | AUROC conf. | estabilidade* |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        print(f"| `{r['backend']}` | {GROUP.get(r['kind'], r['kind'])} | {f(r['accuracy'], True)} "
              f"| {f(r['false_activation_rate'], True)} | {f(r['missed_rate'], True)} "
              f"| {f(r['intent_accuracy_when_addressed'], True)} | {r['latency_ms']['p50']:.0f} ms "
              f"| {r['latency_ms']['p95']:.0f} ms | {r['cpu_seconds_per_decision']:.2f} | {f(r['ece'], digits=2)} "
              f"| {f(r['auroc_confidence'], digits=2)} | {f(r.get('perturbation_agreement'), True)} |")
    print("\n\\* concordância da decisão entre a fala original e a mesma fala sem acentos/pontuação/maiúsculas.\n")

    print("## Acurácia por fatia (tags)\n")
    tags = ["clear", "hard", "ambiguous", "short", "long", "asr", "no_wake", "mentions_wake", "near_wake",
            "background", "to_human", "english"]
    print("| backend | " + " | ".join(tags) + " |")
    print("|---|" + "---|" * len(tags))
    for r in rows:
        cells = [f(r["by_tag"].get(t, {}).get("accuracy"), True) for t in tags]
        print(f"| `{r['backend']}` | " + " | ".join(cells) + " |")
    n = {t: rows[0]["by_tag"].get(t, {}).get("n", 0) for t in tags} if rows else {}
    print("\nN por fatia: " + ", ".join(f"{t}={n[t]}" for t in tags) + "\n")

    print("## Acurácia por classe\n")
    labels = sorted(rows[0]["by_label"]) if rows else []
    print("| backend | " + " | ".join(labels) + " |")
    print("|---|" + "---|" * len(labels))
    for r in rows:
        print(f"| `{r['backend']}` | " + " | ".join(f(r["by_label"][k]["accuracy"], True) for k in labels) + " |")

    print("\n## Economia de LLM (rotas knowledge/complex)\n")
    print("| backend | chamadas ao LLM | evitadas vs. mandar tudo | necessárias | perdidas | desperdiçadas |")
    print("|---|---|---|---|---|---|")
    for r in rows:
        e = r["llm"]
        print(f"| `{r['backend']}` | {e['llm_calls']}/{e['llm_calls_if_no_router']} | {f(e['calls_avoided_pct'], True)} "
              f"| {e['llm_needed']} | {e['llm_missed']} | {e['llm_wasted']} |")

    print("\n## Limiar de confiança (política: abaixo do limiar → ignorar)\n")
    for r in rows:
        if r.get("score_kind") and "probability" in r["score_kind"] and r.get("threshold_sweep"):
            pts = " · ".join(f"τ={p['threshold']:.2f}: acc {f(p['accuracy'], True)}, FA {f(p['false_activation_rate'], True)}, "
                             f"perdidos {f(p['missed_rate'], True)}" for p in r["threshold_sweep"] if p["threshold"] in (0.0, 0.5, 0.7, 0.9))
            print(f"- `{r['backend']}`: {pts}")

    print("\n## Custo e memória\n")
    print("| backend | modelo | CPU-s/decisão | núcleos ocupados | RSS servidor | carga |")
    print("|---|---|---|---|---|---|")
    for r in rows:
        rss = r["rss_mb"]["server"] or f"+{r['rss_mb']['lab_process_delta']} (no processo do lab)"
        print(f"| `{r['backend']}` | {r['model']} | {r['cpu_seconds_per_decision']:.3f} | {r['cpu_cores_busy']:.1f} "
              f"| {rss} MB | {r['load_seconds']:.1f} s |")

    scaling = BENCH / "scaling.json"
    if scaling.exists():
        data = json.loads(scaling.read_text())
        print("\n## Escalonamento de intenções (classes definidas na requisição; 60 falas)\n")
        print("| backend | cenário | opções | acurácia | falsa ativação | perdidos | escolheu distrator | p50 |")
        print("|---|---|---|---|---|---|---|---|")
        for name, scen in data.items():
            for key, s in scen.items():
                print(f"| `{name}` | {key} | {s['n_options']} | {f(s['accuracy'], True)} | {f(s['false_activation_rate'], True)} "
                      f"| {f(s['missed_rate'], True)} | {f(s['picked_distractor'], True)} | {s['latency_p50_ms']:.0f} ms |")

    pipeline = BENCH / "pipeline.json"
    if pipeline.exists():
        data = json.loads(pipeline.read_text())
        print("\n## Fase 2 — router na frente do LLM (ponta a ponta pela API)\n")
        print("| estratégia | falas | tempo total | só decisões | só LLM | chamadas LLM | necessárias | desperdiçadas | perdidas | falsa ativação |")
        print("|---|---|---|---|---|---|---|---|---|---|")
        for key, s in data.items():
            print(f"| {s['router']}{' τ=' + str(s['threshold']) if 'threshold' in s else ''} | {s['n']} | {s['total_seconds']:.0f} s "
                  f"| {s.get('decision_seconds', 0):.0f} s | {s.get('llm_seconds', s['total_seconds']):.0f} s | {s['llm_calls']} "
                  f"| {s['llm_calls_needed']} | {s['llm_wasted']} | {s.get('llm_missed', 0)} | {f(s.get('false_activation_rate'), True)} |")


if __name__ == "__main__":
    main()
