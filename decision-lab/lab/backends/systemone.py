"""Cliente genérico do formato "System One" (POST /v1/systemone), o formato introduzido pelo Jev.

Serve para qualquer modelo de decisão que fale esse protocolo: jeff-serve (Jeff), llama-server com
modelos de decisão (Julia-1, Laya, Kev, OpenJev...), laya-serve, decider.serve, ollaya, ou o próprio
Jev hospedado (com url/api_key). Trocar o modelo = trocar a URL no config.
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

from lab.backends.base import Backend
from lab.types import Decision, Option, Timer


class SystemOneBackend(Backend):
    kind = "decision-model"

    GATE = {"en": "Is the speaker directly asking the voice assistant Alexa to do something or to answer something "
                  "(as opposed to talking to another person, narrating, or background audio)?",
            "pt": "Quem fala está pedindo diretamente à assistente de voz Alexa que faça ou responda algo (e não "
                  "conversando com outra pessoa, narrando algo ou som de TV ao fundo)?"}

    def __init__(self, name: str, model: str, url: str, request_model: str | None = None,
                 api_key_env: str | None = None, timeout: float = 120.0, port: int | None = None,
                 gate: bool = False, gate_threshold: float = 0.5, **kw: Any) -> None:
        super().__init__(name, model, **kw)
        # gate: pergunta extra (noul) "é dirigido ao assistente?" na mesma requisição; separa
        # "a quem a fala se dirige" de "sobre o que ela é". Custa uma linha a mais de inferência.
        self.gate, self.gate_threshold = gate, gate_threshold
        self.url = url.rstrip("/")
        self.request_model = request_model
        self.port = port
        headers = {}
        if api_key_env and os.getenv(api_key_env):
            headers["Authorization"] = f"Bearer {os.environ[api_key_env]}"
        self.client = httpx.Client(timeout=timeout, headers=headers)

    def request_body(self, text: str, options: list[Option], question: str) -> dict[str, Any]:
        body: dict[str, Any] = {
            "state": text,
            "questions": {"decision": {"type": "choice", "instructions": question,
                                       "criteria": {o.key: o.description for o in options}}},
        }
        if self.gate:
            body["questions"]["addressed"] = {"type": "noul", "instructions": self.GATE[self.option_lang]}
        if self.request_model:
            body["model"] = self.request_model
        return body

    def _decide(self, text: str, options: list[Option], question: str) -> Decision:
        body = self.request_body(text, options, question)
        for attempt in range(20):  # 529/503 = servidor ocupado (jeff-serve atende uma requisição por vez)
            with Timer() as t:
                response = self.client.post(f"{self.url}/v1/systemone", json=body)
            if response.status_code not in (529, 503):
                break
            time.sleep(0.25 * (attempt + 1))
        if response.status_code != 200:
            raise RuntimeError(f"{self.name}: HTTP {response.status_code}: {response.text[:300]}")
        data = response.json()
        answer = data["answers"]["decision"]
        probabilities = answer.get("probabilities") or {answer["choice"]: 1.0}
        if self.gate and "ignore" in probabilities:
            p_addr = float(data["answers"]["addressed"]["noul"])
            # combina: P(ignore) = 1 - P(dirigido); intenções repartem P(dirigido) proporcionalmente
            rest = {k: v for k, v in probabilities.items() if k != "ignore"}
            z = sum(rest.values()) or 1.0
            probabilities = {"ignore": 1 - p_addr, **{k: p_addr * v / z for k, v in rest.items()}}
            choice = "ignore" if p_addr < self.gate_threshold else max(rest, key=rest.__getitem__)
            return Decision(choice, probabilities[choice], probabilities, "probability", t.ms, self.name,
                            data.get("model", self.model),
                            {"usage": data.get("usage"), "p_addressed": p_addr, "intent_raw": answer["choice"]})
        return Decision(
            # confidence = probabilidade da opção escolhida (é o que a calibração promete). O campo
            # "confidence" do protocolo é outra métrica (depende do servidor) e fica nos metadados.
            decision=answer["choice"], confidence=probabilities.get(answer["choice"]),
            scores=probabilities, score_kind="probability",
            latency_ms=t.ms, backend=self.name, model=data.get("model", self.model),
            metadata={"usage": data.get("usage"), "protocol_confidence": answer.get("confidence")},
        )
