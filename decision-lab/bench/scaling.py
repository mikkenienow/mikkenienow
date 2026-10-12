"""O que acontece quando o número de intenções cresce, ou quando as classes mudam em tempo de requisição?

  .venv/bin/python -m bench.scaling --backends jeff-0.8b,julia-1 --limit 60

Cenários (todas as classes são passadas NA REQUISIÇÃO; nenhum modelo é re-treinado):
  n6   — a taxonomia base (6 opções)
  n12, n20, n32 — base + intenções "distratoras" plausíveis em casa, que não correspondem a nenhum item
           do teste: escolher uma delas é erro. Mede degradação de acurácia e custo por opção.
  gate — redefinição dinâmica: só 2 opções (ignorar vs. pedido ao assistente) — o "porteiro" puro.
Backends treinados (tfidf, e5-logreg, e5-knn) não entram: não conseguem decidir classes que não viram.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bench import bench_dir  # noqa: E402
from bench.metrics import binary_metrics, correct, percentile  # noqa: E402
from bench.run_bench import load_test  # noqa: E402
from lab import backends as registry  # noqa: E402
from lab.taxonomy import Taxonomy  # noqa: E402
from lab.types import Option  # noqa: E402

DISTRACTORS = [  # (chave, pt, en)
    ("shopping_list", "Lista de compras: adicionar ou remover itens", "Shopping list: add or remove items"),
    ("phone_call", "Fazer uma ligação telefônica para um contato", "Make a phone call to a contact"),
    ("security_camera", "Mostrar câmeras de segurança ou a campainha", "Show security cameras or the doorbell"),
    ("robot_vacuum", "Controlar o robô aspirador", "Control the robot vacuum"),
    ("pet_feeder", "Alimentador automático do animal de estimação", "Automatic pet feeder"),
    ("irrigation", "Irrigação do jardim", "Garden irrigation"),
    ("car", "Carro conectado: destravar, ver bateria ou combustível", "Connected car: unlock, check battery or fuel"),
    ("package_tracking", "Rastrear entregas e encomendas", "Track deliveries and parcels"),
    ("banking", "Banco: consultar saldo ou pagar contas", "Banking: check balance or pay bills"),
    ("food_delivery", "Pedir comida por aplicativo de delivery", "Order food from a delivery app"),
    ("ride_hailing", "Chamar um carro por aplicativo", "Call a ride-hailing car"),
    ("intercom", "Anunciar uma mensagem em outro cômodo pelo interfone", "Announce a message in another room via intercom"),
    ("baby_monitor", "Monitor de bebê", "Baby monitor"),
    ("energy_report", "Relatório de consumo de energia da casa", "Home energy consumption report"),
    ("water_heater", "Aquecedor de água ou boiler", "Water heater or boiler"),
    ("pool", "Piscina: bomba e aquecimento", "Pool: pump and heating"),
    ("printer", "Imprimir um documento", "Print a document"),
    ("fitness", "Registrar exercícios ou passos", "Log exercise or steps"),
    ("meditation", "Guiar uma meditação ou exercício de respiração", "Guide a meditation or breathing exercise"),
    ("trivia_game", "Jogar um jogo de perguntas com o assistente", "Play a quiz game with the assistant"),
    ("assistant_settings", "Configurações do próprio assistente: Wi-Fi, idioma, voz", "Assistant settings: Wi-Fi, language, voice"),
    ("store_orders", "Pedidos e compras na loja online", "Online store orders and purchases"),
    ("emergency", "Chamar emergência: polícia, bombeiros, ambulância", "Call emergency services"),
    ("find_phone", "Encontrar meu celular fazendo ele tocar", "Find my phone by making it ring"),
    ("ev_charger", "Carregador do carro elétrico", "Electric car charger"),
    ("quick_note", "Anotar uma nota rápida", "Take a quick note"),
]

GATE = {
    "pt": [("ignore", "Não é um pedido ao assistente (conversa entre pessoas, TV, comentário)"),
           ("request", "É um pedido, comando ou pergunta dirigido ao assistente Alexa")],
    "en": [("ignore", "Not a request to the assistant (people talking, TV, a remark)"),
           ("request", "A request, command or question addressed to the assistant Alexa")],
}


def scenario_options(taxonomy: Taxonomy, lang: str, scenario: str) -> list[Option]:
    if scenario == "gate":
        return [Option(k, d) for k, d in GATE[lang]]
    extra = int(scenario[1:]) - 6
    return taxonomy.options(lang) + [Option(k, pt if lang == "pt" else en) for k, pt, en in DISTRACTORS[:extra]]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backends", required=True)
    parser.add_argument("--scenarios", default="gate,n6,n12,n20,n32")
    parser.add_argument("--limit", type=int, default=60)
    args = parser.parse_args()
    taxonomy, config = Taxonomy.load(), registry.load_config()
    rows = load_test(args.limit)
    results: dict[str, Any] = {}
    out_path = bench_dir() / "scaling.json"
    if out_path.exists():
        results = json.loads(out_path.read_text())
    for name in args.backends.split(","):
        backend = registry.create(name, config)
        question = taxonomy.question(backend.option_lang)
        results.setdefault(name, {})
        for scenario in args.scenarios.split(","):
            options = scenario_options(taxonomy, backend.option_lang, scenario)
            backend.warmup(options, question)
            preds = []
            for row in rows:
                d = backend.decide(row["text"], options, question)
                decision = d.decision
                if scenario == "gate":  # avaliação binária: request vale para qualquer classe não-ignore
                    decision = "ignore" if d.decision == "ignore" else next((a for a in row["accept"] if a != "ignore"), "x")
                preds.append({**row, "decision": decision, "confidence": d.confidence, "latency_ms": d.latency_ms,
                              "raw": d.decision})
            lat = [p["latency_ms"] for p in preds]
            r = {"n_options": len(options), "accuracy": sum(map(correct, preds)) / len(preds),
                 **binary_metrics(preds), "latency_p50_ms": percentile(lat, 0.5), "latency_p95_ms": percentile(lat, 0.95),
                 "picked_distractor": sum(p["raw"] in {k for k, _, _ in DISTRACTORS} for p in preds) / len(preds)}
            results[name][scenario] = r
            print(f"{name:22s} {scenario:5s} opts={len(options):2d} acc={r['accuracy']:.3f} "
                  f"FA={r['false_activation_rate']:.3f} miss={r['missed_rate']:.3f} "
                  f"distrator={r['picked_distractor']:.3f} p50={r['latency_p50_ms']:.0f}ms", flush=True)
            out_path.write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
