"""Backends que rodam dentro do processo do laboratório (PyTorch/scikit-learn).

Zero-shot (aceitam classes dinâmicas):
  NliBackend          — mDeBERTa NLI: 1 forward por opção ("esta fala é sobre <descrição>?")
  GliClassBackend     — GLiClass: 1 forward com todas as opções (rótulos independentes, sigmoide)
  EmbedZeroShotBackend— similaridade de embedding entre fala e descrição da opção
Treinados (classificador tradicional; só as classes vistas no treino):
  TfidfBackend        — TF-IDF (n-gramas de caractere e palavra) + regressão logística
  EmbedLogRegBackend  — embedding (e5) + regressão logística
  EmbedKnnBackend     — "semantic router": classe do exemplo de treino mais parecido
"""

from __future__ import annotations

import threading
from functools import lru_cache
from typing import Any

import numpy as np
import torch

from lab.backends.base import Backend, option_text, softmax
from lab.taxonomy import ROOT
from lab.types import Decision, Option, Timer

_LOCK = threading.Lock()  # torch na CPU: uma inferência por vez dá latência mais estável


def model_path(name: str) -> str:
    local = ROOT / "models" / "hf" / name.split("/")[-1]
    return str(local) if local.exists() else name


@lru_cache(maxsize=4)
def sentence_model(name: str):  # type: ignore[no-untyped-def]
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model_path(name), device="cpu")


class _Embedder:
    """multilingual-e5 espera prefixos 'query: ' / 'passage: '."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.e5 = "e5" in model_name

    def encode(self, texts: list[str], kind: str = "query") -> np.ndarray:
        if self.e5:
            texts = [f"{kind}: {t}" for t in texts]
        with _LOCK:
            return sentence_model(self.model_name).encode(texts, normalize_embeddings=True, convert_to_numpy=True)


class NliBackend(Backend):
    kind = "zero-shot-nli"

    def __init__(self, name: str, model: str, hypothesis: str = "Neste caso, o assistente deve: {}.", **kw: Any) -> None:
        super().__init__(name, model, **kw)
        from transformers import pipeline
        self.pipe = pipeline("zero-shot-classification", model=model_path(model), device="cpu", dtype=torch.float32)
        self.hypothesis = hypothesis

    def _decide(self, text: str, options: list[Option], question: str) -> Decision:
        labels = [option_text(o) for o in options]
        with _LOCK, Timer() as t:
            out = self.pipe(text, candidate_labels=labels, hypothesis_template=self.hypothesis, multi_label=False)
        by_label = dict(zip(out["labels"], out["scores"]))
        probs = {o.key: float(by_label[option_text(o)]) for o in options}
        choice = max(probs, key=probs.__getitem__)
        # softmax dos logits de "entailment" entre opções: parece probabilidade, mas não é calibrada
        return Decision(choice, probs[choice], probs, "pseudo_probability", t.ms, self.name, self.model,
                        {"forward_passes": len(options)})


class GliClassBackend(Backend):
    kind = "zero-shot-gliclass"

    def __init__(self, name: str, model: str, use_descriptions: bool = True, **kw: Any) -> None:
        super().__init__(name, model, **kw)
        from gliclass import GLiClassModel, ZeroShotClassificationPipeline
        from transformers import AutoTokenizer
        path = model_path(model)
        self.pipe = ZeroShotClassificationPipeline(
            GLiClassModel.from_pretrained(path).float(), AutoTokenizer.from_pretrained(path, add_prefix_space=True),
            classification_type="multi-label", device="cpu")
        self.use_descriptions = use_descriptions

    def _decide(self, text: str, options: list[Option], question: str) -> Decision:
        labels = [option_text(o) if self.use_descriptions else o.key for o in options]
        with _LOCK, Timer() as t:
            with torch.inference_mode():
                out = self.pipe(text, labels, threshold=0.0)[0]
        by_label = {r["label"]: float(r["score"]) for r in out}
        raw = {o.key: by_label.get(label, 0.0) for o, label in zip(options, labels)}
        total = sum(raw.values()) or 1.0
        scores = {k: v / total for k, v in raw.items()}
        choice = max(raw, key=raw.__getitem__)
        # sigmoides independentes por rótulo; a confiança é o sigmoide do vencedor
        return Decision(choice, raw[choice], scores, "pseudo_probability", t.ms, self.name, self.model,
                        {"raw_sigmoid": raw})


class EmbedZeroShotBackend(Backend):
    kind = "zero-shot-embedding"

    def __init__(self, name: str, model: str, temperature: float = 0.02, **kw: Any) -> None:
        super().__init__(name, model, **kw)
        self.embedder, self.temperature = _Embedder(model), temperature
        self._cache: dict[tuple[str, ...], np.ndarray] = {}

    def _decide(self, text: str, options: list[Option], question: str) -> Decision:
        key = tuple(option_text(o) for o in options)
        with Timer() as t:
            if key not in self._cache:  # descrições das opções: embutidas uma vez e reutilizadas
                self._cache[key] = self.embedder.encode(list(key), "passage")
            q = self.embedder.encode([text], "query")[0]
            sims = {o.key: float(s) for o, s in zip(options, self._cache[key] @ q)}
        probs = softmax(sims, self.temperature)
        choice = max(probs, key=probs.__getitem__)
        return Decision(choice, sims[choice], probs, "similarity", t.ms, self.name, self.model,
                        {"cosine": sims})


class _Trained(Backend):
    dynamic_options = False

    def check(self, options: list[Option]) -> None:
        unknown = [o.key for o in options if o.key not in self.classes]
        if unknown:
            raise ValueError(f"{self.name} só conhece as classes do treino; desconhecidas: {unknown}")

    def restrict(self, probs: dict[str, float], options: list[Option]) -> dict[str, float]:
        """Se a requisição pede um subconjunto das classes, renormaliza sobre ele."""
        keys = [o.key for o in options]
        total = sum(probs[k] for k in keys) or 1.0
        return {k: probs[k] / total for k in keys}


class TfidfBackend(_Trained):
    kind = "trained-tfidf"

    def __init__(self, name: str, model: str = "tfidf+logreg", **kw: Any) -> None:
        super().__init__(name, model, **kw)
        self.classes: list[str] = []

    def fit(self, texts: list[str], labels: list[str]) -> None:
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline, make_union
        from sklearn.feature_extraction.text import TfidfVectorizer
        self.pipe = make_pipeline(
            make_union(TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True, lowercase=True),
                       TfidfVectorizer(analyzer="word", ngram_range=(1, 2), sublinear_tf=True, lowercase=True)),
            LogisticRegression(C=20, max_iter=2000))
        self.pipe.fit(texts, labels)
        self.classes = list(self.pipe.classes_)

    def _decide(self, text: str, options: list[Option], question: str) -> Decision:
        self.check(options)
        with Timer() as t:
            p = self.pipe.predict_proba([text])[0]
        probs = self.restrict(dict(zip(self.classes, map(float, p))), options)
        choice = max(probs, key=probs.__getitem__)
        return Decision(choice, probs[choice], probs, "pseudo_probability", t.ms, self.name, self.model, {})


class EmbedLogRegBackend(_Trained):
    kind = "trained-embedding"

    def __init__(self, name: str, model: str, **kw: Any) -> None:
        super().__init__(name, model, **kw)
        self.embedder, self.classes = _Embedder(model), []

    def fit(self, texts: list[str], labels: list[str]) -> None:
        from sklearn.linear_model import LogisticRegression
        self.clf = LogisticRegression(C=10, max_iter=2000).fit(self.embedder.encode(texts), labels)
        self.classes = list(self.clf.classes_)

    def _decide(self, text: str, options: list[Option], question: str) -> Decision:
        self.check(options)
        with Timer() as t:
            p = self.clf.predict_proba(self.embedder.encode([text]))[0]
        probs = self.restrict(dict(zip(self.classes, map(float, p))), options)
        choice = max(probs, key=probs.__getitem__)
        return Decision(choice, probs[choice], probs, "pseudo_probability", t.ms, self.name, self.model, {})


class EmbedKnnBackend(_Trained):
    """Estilo aurelio semantic-router: cada rota tem frases-exemplo; vence a mais parecida."""
    kind = "trained-knn"

    def __init__(self, name: str, model: str, temperature: float = 0.02, **kw: Any) -> None:
        super().__init__(name, model, **kw)
        self.embedder, self.temperature, self.classes = _Embedder(model), temperature, []

    def fit(self, texts: list[str], labels: list[str]) -> None:
        self.matrix, self.labels = self.embedder.encode(texts), labels
        self.classes = sorted(set(labels))

    def _decide(self, text: str, options: list[Option], question: str) -> Decision:
        self.check(options)
        with Timer() as t:
            sims = self.matrix @ self.embedder.encode([text])[0]
        best: dict[str, float] = {}
        for label, s in zip(self.labels, sims):
            best[label] = max(best.get(label, -1.0), float(s))
        best = {o.key: best[o.key] for o in options}
        probs = softmax(best, self.temperature)
        choice = max(best, key=best.__getitem__)
        return Decision(choice, best[choice], probs, "similarity", t.ms, self.name, self.model, {"cosine": best})
