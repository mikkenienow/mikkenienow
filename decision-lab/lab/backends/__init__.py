"""Registro de backends. Um backend é criado a partir de uma entrada de config/backends.yaml."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from lab.backends.base import Backend
from lab.taxonomy import ROOT

TYPES = {
    "systemone": ("lab.backends.systemone", "SystemOneBackend"),
    "llm_logprob": ("lab.backends.llm", "LlmLogprobBackend"),
    "llm_generative": ("lab.backends.llm", "LlmGenerativeBackend"),
    "nli": ("lab.backends.local", "NliBackend"),
    "gliclass": ("lab.backends.local", "GliClassBackend"),
    "embed_zeroshot": ("lab.backends.local", "EmbedZeroShotBackend"),
    "tfidf": ("lab.backends.local", "TfidfBackend"),
    "embed_logreg": ("lab.backends.local", "EmbedLogRegBackend"),
    "embed_knn": ("lab.backends.local", "EmbedKnnBackend"),
    "cascade": ("lab.backends.cascade", "CascadeBackend"),
}


def load_config(path: str | Path = ROOT / "config" / "backends.yaml") -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text())


def train_examples() -> tuple[list[str], list[str]]:
    rows = [json.loads(line) for line in (ROOT / "data" / "train.jsonl").read_text().splitlines()]
    return [r["text"] for r in rows], [r["label"] for r in rows]


def create(name: str, config: dict[str, Any] | None = None) -> Backend:
    config = config or load_config()
    spec = dict(config["backends"][name])
    module_name, class_name = TYPES[spec.pop("type")]
    module = __import__(module_name, fromlist=[class_name])
    backend: Backend = getattr(module, class_name)(name=name, **spec)
    if not backend.dynamic_options:
        backend.fit(*train_examples())
    return backend
