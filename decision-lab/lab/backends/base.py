"""Interface comum dos backends de decisão."""

from __future__ import annotations

import math
from typing import Any

from lab.types import Decision, Option


class Backend:
    """Um motor de decisão. Subclasses implementam _decide()."""

    kind = "abstract"
    # True: aceita opções definidas na requisição (zero-shot). False: só as classes vistas no fit().
    dynamic_options = True
    # Porta do servidor externo (para contabilizar CPU do processo que realmente faz a inferência).
    port: int | None = None

    def __init__(self, name: str, model: str, option_lang: str = "pt", **_: Any) -> None:
        self.name = name
        self.model = model
        self.option_lang = option_lang

    def fit(self, texts: list[str], labels: list[str]) -> None:  # para backends treináveis
        pass

    def warmup(self, options: list[Option], question: str) -> None:
        self.decide("Alexa, acende a luz da sala", options, question)

    def decide(self, text: str, options: list[Option], question: str) -> Decision:
        if not options:
            raise ValueError("ao menos uma opção é necessária")
        return self._decide(text, options, question)

    def _decide(self, text: str, options: list[Option], question: str) -> Decision:
        raise NotImplementedError

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "kind": self.kind, "model": self.model,
                "dynamic_options": self.dynamic_options, "option_lang": self.option_lang, "port": self.port}


def softmax(values: dict[str, float], temperature: float = 1.0) -> dict[str, float]:
    m = max(values.values())
    exps = {k: math.exp((v - m) / temperature) for k, v in values.items()}
    z = sum(exps.values())
    return {k: v / z for k, v in exps.items()}


def top(scores: dict[str, float]) -> tuple[str, float]:
    key = max(scores, key=scores.__getitem__)
    return key, scores[key]


def option_text(option: Option) -> str:
    return option.description or option.key
