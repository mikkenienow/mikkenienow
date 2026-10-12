"""Consumidores das decisões: o "segundo componente" que age a partir da rota escolhida.

Tudo aqui é simulado (sem hardware): uma casa com dispositivos, um player de mídia e timers.
O executor LLM chama de verdade um LLM local (llama-server) — é a Fase 2 (modelo de decisão -> LLM).
"""

from __future__ import annotations

import re
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any

import httpx


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


DEVICES = {  # padrão (regex sobre texto normalizado) -> dispositivo
    r"\bluz|lus|luiz|lampada|ilumina": "luz", r"\bar\b|ar.condicionado|aquecedor": "clima",
    r"\btv\b|televis|teve|tevê": "tv", r"cortina|persiana": "cortina", r"porta|tranca": "porta",
    r"portao": "portao", r"ventilador": "ventilador", r"cafeteira": "cafeteira", r"maquina": "maquina",
    r"tomada": "tomada",
}
ROOMS = ["sala", "quarto", "cozinha", "banheiro", "varanda", "garagem", "escritorio", "corredor", "frente"]
ON = r"\b(acend|lig|abr|ativ|turn on|liga)"
OFF = r"\b(apag|deslig|fech|tranc|turn off|desativ)"


@dataclass
class Home:
    devices: dict[str, str] = field(default_factory=dict)
    media: dict[str, Any] = field(default_factory=lambda: {"playing": None, "volume": 5})
    timers: list[dict[str, Any]] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {"devices": dict(self.devices), "media": dict(self.media), "timers": list(self.timers)}

    # --- HOME_AUTOMATION: extração de slots simples por regras (o modelo já decidiu O QUE é) ---
    def home_automation(self, text: str) -> dict[str, Any]:
        t = _norm(text)
        device = next((d for pat, d in DEVICES.items() if re.search(pat, t)), "luz")
        rooms = [r for r in ROOMS if r in t] or ["sala"]
        if "tudo" in t or "todas" in t:
            rooms = ["*"]
        state = "off" if re.search(OFF, t) else "on" if re.search(ON, t) else "ajustar"
        if re.search(r"escuro", t):
            state = "on"
        with self.lock:
            for room in rooms:
                self.devices[f"{device}:{room}"] = state
        return {"device": device, "rooms": rooms, "state": state}

    def media_control(self, text: str) -> dict[str, Any]:
        t = _norm(text)
        with self.lock:
            if re.search(r"aument|alto|maximo", t):
                self.media["volume"] = min(10, self.media["volume"] + 2)
            elif re.search(r"abaix|abax|baixo", t):
                self.media["volume"] = max(0, self.media["volume"] - 2)
            elif m := re.search(r"volume (\d+)", t):
                self.media["volume"] = int(m.group(1))
            elif re.search(r"\b(pausa|para)\b", t):
                self.media["playing"] = None
            else:
                self.media["playing"] = text
            return dict(self.media)

    def timer(self, text: str) -> dict[str, Any]:
        entry = {"created": time.strftime("%H:%M:%S"), "request": text}
        with self.lock:
            self.timers.append(entry)
            self.timers[:] = self.timers[-10:]
        return entry


class LlmExecutor:
    """Responde de verdade com um LLM local (OpenAI-compatible do llama-server)."""

    def __init__(self, url: str, model: str, max_tokens: int = 96) -> None:
        self.url, self.model, self.max_tokens = url.rstrip("/"), model, max_tokens
        self.client = httpx.Client(timeout=600)

    def answer(self, text: str) -> dict[str, Any]:
        body = {"messages": [{"role": "system", "content": "Você é um assistente de voz doméstico. Responda em "
                              "português, de forma curta e falada (2-3 frases)."},
                             {"role": "user", "content": text}],
                "temperature": 0.3, "max_tokens": self.max_tokens, "chat_template_kwargs": {"enable_thinking": False}}
        start = time.perf_counter()
        data = self.client.post(f"{self.url}/v1/chat/completions", json=body).json()
        ms = (time.perf_counter() - start) * 1000
        usage = data.get("usage", {})
        return {"answer": data["choices"][0]["message"]["content"], "llm": self.model, "llm_latency_ms": round(ms),
                "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens")}
