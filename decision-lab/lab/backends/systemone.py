"""Cliente genérico do formato "System One" (POST /v1/systemone), o formato introduzido pelo Jev.

Serve para qualquer modelo de decisão que fale esse protocolo: jeff-serve (Jeff), llama-server com
modelos de decisão (Julia-1, Laya, Kev, OpenJev...), laya-serve, decider.serve, ollaya, ou o próprio
Jev hospedado (com url/api_key). Trocar o modelo = trocar a URL no config.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from lab.backends.base import Backend
from lab.types import Decision, Option, Timer


class SystemOneBackend(Backend):
    kind = "decision-model"

    def __init__(self, name: str, model: str, url: str, request_model: str | None = None,
                 api_key_env: str | None = None, timeout: float = 120.0, port: int | None = None, **kw: Any) -> None:
        super().__init__(name, model, **kw)
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
        if self.request_model:
            body["model"] = self.request_model
        return body

    def _decide(self, text: str, options: list[Option], question: str) -> Decision:
        body = self.request_body(text, options, question)
        with Timer() as t:
            response = self.client.post(f"{self.url}/v1/systemone", json=body)
        if response.status_code != 200:
            raise RuntimeError(f"{self.name}: HTTP {response.status_code}: {response.text[:300]}")
        data = response.json()
        answer = data["answers"]["decision"]
        probabilities = answer.get("probabilities") or {answer["choice"]: 1.0}
        return Decision(
            # confidence = probabilidade da opção escolhida (é o que a calibração promete). O campo
            # "confidence" do protocolo é outra métrica (depende do servidor) e fica nos metadados.
            decision=answer["choice"], confidence=probabilities.get(answer["choice"]),
            scores=probabilities, score_kind="probability",
            latency_ms=t.ms, backend=self.name, model=data.get("model", self.model),
            metadata={"usage": data.get("usage"), "protocol_confidence": answer.get("confidence")},
        )
