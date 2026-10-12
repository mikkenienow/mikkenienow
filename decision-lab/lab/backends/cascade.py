"""Cascata: um backend barato decide sozinho quando está confiante; abaixo de τ, escala para um mais caro.

É o padrão "System 1 rápido na frente, modelo maior só quando há dúvida" aplicado ao próprio porteiro.
A confiança do primeiro estágio precisa ser um sinal útil (AUROC alto) para isso funcionar.
"""

from __future__ import annotations

from typing import Any

from lab.backends.base import Backend
from lab.types import Decision, Option


class CascadeBackend(Backend):
    kind = "cascade"

    def __init__(self, name: str, first: str, second: str, threshold: float = 0.3,
                 model: str | None = None, **kw: Any) -> None:
        from lab import backends as registry
        self.first, self.second = registry.create(first), registry.create(second)
        super().__init__(name, model or f"{first} -> {second} (τ={threshold})",
                         option_lang=kw.pop("option_lang", self.second.option_lang), **kw)
        self.threshold = threshold
        self.dynamic_options = self.first.dynamic_options
        self.port = self.second.port

    def _decide(self, text: str, options: list[Option], question: str) -> Decision:
        from lab.taxonomy import Taxonomy
        tax = Taxonomy.load()
        first = self.first.decide(text, tax.options(self.first.option_lang) if not self.first.dynamic_options
                                  else options, question)
        if first.confidence is not None and first.confidence >= self.threshold:
            first.backend, first.model = self.name, self.model
            first.metadata = {**first.metadata, "stage": 1, "stage1": self.first.name}
            return first
        # perguntas/opções no idioma que o segundo estágio prefere
        second = self.second.decide(text, tax.options(self.second.option_lang), tax.question(self.second.option_lang))
        second.latency_ms += first.latency_ms
        second.backend, second.model = self.name, self.model
        second.metadata = {**second.metadata, "stage": 2, "stage1_decision": first.decision,
                           "stage1_confidence": first.confidence}
        return second
