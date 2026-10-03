"""Tipos comuns do laboratório. Todo backend recebe opções e devolve uma Decision."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Option:
    key: str
    description: str | None = None


@dataclass
class Decision:
    decision: str
    # Confiança do backend na decisão. O SIGNIFICADO depende de score_kind: só "probability" é uma
    # probabilidade calibrada sobre as opções; os demais são sinais que precisam de threshold próprio.
    confidence: float | None
    scores: dict[str, float] | None
    score_kind: str  # probability | pseudo_probability | similarity | token_probability | none
    latency_ms: float
    backend: str
    model: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_options(raw: Any) -> list[Option]:
    """Aceita ["a", "b"], {"a": "desc", "b": None} ou [{"key": "a", "description": "..."}]."""
    if isinstance(raw, dict):
        return [Option(str(k), None if v is None else str(v)) for k, v in raw.items()]
    if isinstance(raw, list):
        out = []
        for item in raw:
            if isinstance(item, str):
                out.append(Option(item))
            elif isinstance(item, dict) and "key" in item:
                out.append(Option(str(item["key"]), item.get("description")))
            else:
                raise ValueError(f"opção inválida: {item!r}")
        return out
    raise ValueError("options deve ser lista ou objeto")


class Timer:
    def __enter__(self) -> "Timer":
        self.start = time.perf_counter()
        return self

    def __exit__(self, *exc: object) -> None:
        self.ms = (time.perf_counter() - self.start) * 1000
