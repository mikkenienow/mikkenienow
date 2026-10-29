"""Verificação ponta a ponta pela API HTTP, do ponto de vista de um cliente (o celular, ou este script).

  .venv/bin/python -m bench.phase3_check                                   # localhost:8000
  .venv/bin/python -m bench.phase3_check --base http://192.168.1.169:8000  # pelo mesmo caminho do celular (portproxy)
  .venv/bin/python -m bench.phase3_check --sse-seconds 600                 # + 10 min de stream aberto

Mede e confere, pela rede:
  1. conectividade e ping (GET /health)
  2. o ciclo decisão -> ferramenta -> resultado (POST /v1/act), com latência de ida e volta
  3. uma ação sensível: fica pendente, outro cliente não confirma, o dono confirma
  4. um timer real: criado pela API e o evento "timer_fired" chega pelo stream (SSE)
  5. o stream fica aberto pelo tempo pedido, sem cair
  6. o julgamento humano (POST /v1/feedback) é aceito
Resultado em runs/phase3/<rótulo>.json. Sai com código 1 se alguma checagem falhar.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lab.taxonomy import ROOT  # noqa: E402

# (fala, ferramenta esperada, status esperado) — falas novas, fora do dataset congelado
CASES = [
    ("Alexa, que horas são agora?", "info.time", "executed"),
    ("Alexa, que dia da semana é hoje?", "info.date", "executed"),
    ("Alexa, como está o uso de memória do computador?", "info.system_status", "executed"),
    ("Alexa, acende a luz do escritório", "home.set_device", "executed"),
    ("Alexa, desliga a TV do quarto", "home.set_device", "executed"),
    ("Alexa, toca um samba antigo", "media.play", "executed"),
    ("Alexa, volume 4", "media.set_volume", "executed"),
    ("Alexa, me lembra de regar as plantas da varanda", "note.add", "executed"),
    ("Alexa, o que eu tenho anotado?", "note.list", "executed"),
    ("Você viu que horas ele chegou ontem?", None, "ignored"),
    ("Mãe, cadê o controle da televisão?", None, "ignored"),
    ("Alexa, a luz", "home.set_device", "needs_info"),
]


def pct(values: list[float], q: float) -> float:
    values = sorted(values)
    return round(values[min(len(values) - 1, int(q * len(values)))], 1)


class Stream(threading.Thread):
    """Mantém GET /v1/events aberto e guarda os eventos."""

    def __init__(self, base: str) -> None:
        super().__init__(daemon=True)
        self.base, self.events, self.error, self.opened, self.closed_at = base, [], None, threading.Event(), None
        self.started_at = time.time()

    def run(self) -> None:
        try:
            with httpx.stream("GET", f"{self.base}/v1/events", timeout=httpx.Timeout(10, read=None)) as response:
                self.opened.set()
                for line in response.iter_lines():
                    if line.startswith("data:"):
                        self.events.append({"at": time.time(), **json.loads(line[5:])})
        except Exception as error:  # noqa: BLE001
            self.error = repr(error)
        self.closed_at = time.time()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--backend", default=None)
    parser.add_argument("--label", default=None)
    parser.add_argument("--rounds", type=int, default=3, help="repetições da lista de falas (latência)")
    parser.add_argument("--sse-seconds", type=float, default=30)
    args = parser.parse_args()
    base, me = args.base.rstrip("/"), f"check-{uuid.uuid4().hex[:6]}"
    client = httpx.Client(timeout=120, headers={"user-agent": "phase3-check/1.0"})
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: Any = None) -> bool:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        print(f"{'ok   ' if ok else 'FALHA'} {name}{'' if detail is None else '  ' + str(detail)[:150]}", flush=True)
        return bool(ok)

    def act(text: str, who: str = me) -> tuple[dict[str, Any], float]:
        body = {"input": text, "client": who, "source": "phase3-check", **({"backend": args.backend} if args.backend else {})}
        start = time.perf_counter()
        record = client.post(f"{base}/v1/act", json=body).json()
        return record, (time.perf_counter() - start) * 1000

    # 1. conectividade + ping
    health = client.get(f"{base}/health").json()
    check("servidor responde e o modelo está carregado", health.get("status") == "ok" and not health.get("preloading"), health.get("default_backend"))
    pings = []
    for _ in range(20):
        start = time.perf_counter()
        client.get(f"{base}/health")
        pings.append((time.perf_counter() - start) * 1000)
    tools = client.get(f"{base}/v1/tools").json()
    check("lista de ferramentas é fechada e não tem execução de comando",
          not any(w in t["name"] for t in tools["tools"] for w in ("shell", "exec", "run", "cmd")), f"{len(tools['tools'])} ferramentas, seletor {tools['selector']}")

    stream = Stream(base)
    stream.start()
    check("stream de eventos (SSE) abre", stream.opened.wait(10))

    # 2. ciclo decisão -> ferramenta -> resultado
    act(CASES[0][0])  # aquece
    round_trips, server_ms, wrong = [], [], []
    for _ in range(args.rounds):
        for text, tool, status in CASES:
            record, ms = act(text)
            round_trips.append(ms)
            server_ms.append(record.get("total_ms", record["latency_ms"]))
            got = (record["tool"]["name"], record["tool"]["status"])
            if got != (tool, status):
                wrong.append({"text": text, "expected": [tool, status], "got": list(got), "say": record["tool"].get("say")})
    n = len(CASES) * args.rounds
    check(f"decisão -> ferramenta -> resultado ({n} falas)", len(wrong) <= 0.1 * n, f"{n - len(wrong)}/{n} com o desfecho esperado")
    state = client.get(f"{base}/v1/state").json()
    check("estado da casa mudou de verdade", state["devices"].get("luz:escritorio") == "on" and state["devices"].get("tv:quarto") == "off", state["devices"])
    check("anotação foi gravada no PC", any("regar as plantas" in x["text"] for x in client.get(f"{base}/v1/notes").json()["notes"]))

    # 3. ação sensível
    record, _ = act("Alexa, abre o portão da garagem")
    pending = record["tool"]
    if check("ação sensível fica pendente (não executa)", pending["status"] == "needs_confirmation" and "portao:garagem" not in client.get(f"{base}/v1/state").json()["devices"], pending.get("say")):
        token = pending["confirm"]["token"]
        other = client.post(f"{base}/v1/act/confirm", json={"token": token, "approve": True, "client": "outro-aparelho"}).json()["tool"]
        check("outro cliente não consegue confirmar", other["status"] == "rejected" and "portao:garagem" not in client.get(f"{base}/v1/state").json()["devices"])
        mine = client.post(f"{base}/v1/act/confirm", json={"token": token, "approve": True, "client": me}).json()["tool"]
        check("quem pediu confirma e a ação roda", mine["status"] == "executed" and client.get(f"{base}/v1/state").json()["devices"].get("portao:garagem") == "on", mine.get("say"))
        again = client.post(f"{base}/v1/act/confirm", json={"token": token, "approve": True, "client": me}).json()["tool"]
        check("o mesmo token não vale duas vezes", again["status"] == "rejected")
    def running() -> int:
        return sum(t.get("status") == "running" for t in client.get(f"{base}/v1/state").json()["timers"])

    act("Alexa, timer de 2 minutos")
    before = running()
    record, _ = act("Alexa, cancela todos os timers")
    if check("cancelar timers pede confirmação", record["tool"]["status"] == "needs_confirmation" and running() == before, record["tool"].get("say")):
        spoken, _ = act("não, deixa")
        check("recusa falada cancela o pedido e o timer continua", spoken["tool"]["status"] == "cancelled" and running() == before)
        act("Alexa, cancela todos os timers")
        spoken, _ = act("sim")
        check("confirmação falada executa", spoken["tool"]["status"] == "executed" and running() == 0, spoken["tool"].get("say"))

    # 4. timer real + evento pelo stream
    record, _ = act("Alexa, timer de 3 segundos")
    created = time.time()
    if check("timer real é criado", record["tool"]["status"] == "executed" and record["tool"]["args"].get("seconds") == 3, record["tool"].get("say")):
        timer_id, fired = record["tool"]["result"]["id"], None
        deadline = time.time() + 8
        while time.time() < deadline and fired is None:
            fired = next((e for e in stream.events if e.get("type") == "timer_fired" and e["timer"]["id"] == timer_id), None)
            time.sleep(0.05)
        check("o aviso do timer chega pelo stream", fired is not None, None if fired is None else f"{fired['at'] - created:.2f} s depois de criar (pedido: 3 s)")

    # 6. feedback
    summary = client.post(f"{base}/v1/feedback", json={"decision_id": record["id"], "correct": True, "input": record["input"],
                                                       "decision": record["decision"], "backend": record["backend"]}).json()
    check("julgamento (👍/👎) é aceito", summary.get("n", 0) >= 1)

    # 5. stream aberto pelo tempo pedido
    remaining = args.sse_seconds - (time.time() - stream.started_at)
    if remaining > 0:
        print(f"      mantendo o stream aberto por mais {remaining:.0f} s…", flush=True)
        end = time.time() + remaining
        while time.time() < end and stream.is_alive():
            time.sleep(min(20, max(0.1, end - time.time())))
            act("Alexa, que horas são agora?")  # tráfego periódico: cada fala tem de aparecer no stream
    alive = time.time() - stream.started_at
    seen = sum(e.get("type") == "decision" for e in stream.events)
    check(f"stream ficou aberto {alive:.0f} s sem cair", stream.is_alive() and stream.error is None, f"{len(stream.events)} eventos, {seen} decisões vistas")

    result = {"base": base, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "backend": health.get("default_backend"),
              "tool_selector": tools["selector"],
              "ping_ms": {"p50": pct(pings, 0.5), "p95": pct(pings, 0.95), "n": len(pings)},
              "act_round_trip_ms": {"p50": pct(round_trips, 0.5), "p95": pct(round_trips, 0.95), "mean": round(statistics.fmean(round_trips), 1), "n": len(round_trips)},
              "act_server_ms": {"p50": pct(server_ms, 0.5), "p95": pct(server_ms, 0.95)},
              "overhead_ms_p50": round(pct(round_trips, 0.5) - pct(server_ms, 0.5), 1),
              "sse_seconds": round(alive), "sse_events": len(stream.events), "unexpected": wrong, "checks": checks,
              "passed": all(c["ok"] for c in checks)}
    out = ROOT / "runs" / "phase3"
    out.mkdir(parents=True, exist_ok=True)
    label = args.label or base.split("//")[1].replace(":", "_").replace(".", "-")
    (out / f"{label}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nping p50 {result['ping_ms']['p50']} ms · fala→resultado p50 {result['act_round_trip_ms']['p50']} ms, p95 {result['act_round_trip_ms']['p95']} ms "
          f"· no servidor p50 {result['act_server_ms']['p50']} ms · {'TUDO OK' if result['passed'] else 'HÁ FALHAS'} → runs/phase3/{label}.json")
    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
