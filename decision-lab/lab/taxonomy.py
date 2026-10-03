"""Taxonomia de decisões (classes, descrições PT/EN e rota associada)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from lab.types import Option

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Taxonomy:
    name: str
    questions: dict[str, str]
    raw_options: dict[str, dict[str, str]]

    @classmethod
    def load(cls, path: str | Path = ROOT / "data" / "taxonomy.json") -> "Taxonomy":
        data = json.loads(Path(path).read_text())
        return cls(data["name"], data["question"], data["options"])

    def question(self, lang: str = "pt") -> str:
        return self.questions[lang]

    def options(self, lang: str = "pt") -> list[Option]:
        return [Option(k, v[lang]) for k, v in self.raw_options.items()]

    def route(self, key: str) -> str:
        return self.raw_options.get(key, {}).get("route", "UNKNOWN")

    @property
    def keys(self) -> list[str]:
        return list(self.raw_options)
