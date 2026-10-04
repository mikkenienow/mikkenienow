"""decider em GGUF no llama-server, com o layout schema-first e reaproveitamento do prefixo.

Junta as duas coisas que na CPU só existiam separadas: os kernels nativos do llama.cpp (o Gated DeltaNet do
Qwen3.5 cai num fallback lento no PyTorch) e o cache de schema do decider (as opções vão primeiro; o prefixo
só depende da pergunta e das opções, então é calculado uma vez).

O prompt é montado em ids de tokens, exatamente como decider.prompt.build_schema_first (layout "plain"):

    Question: <pergunta>\nOptions:\n(A) <opção>\n(B) ...     <- prefixo (fixo por schema)
    \n\nContext:\n<fala>\n\nAnswer: (                        <- sufixo (muda a cada fala)

e a decisão é o softmax (com a temperatura do decider_config.json) dos logits das letras no último token.

prefix_cache:
  none     recalcula tudo a cada requisição (mede só o ganho dos kernels do llama.cpp)
  slot     cache_prompt do llama-server: o slot guarda o estado da requisição anterior e reaproveita o prefixo comum
  restore  estado do prefixo salvo em arquivo (POST /slots/0?action=save) e restaurado antes de cada requisição;
           precisa de --slot-save-path no servidor. Sobrevive a reinícios e permite vários schemas num slot só.
"""

from __future__ import annotations

import hashlib
import string
from pathlib import Path
from typing import Any

import httpx

from lab.backends.base import Backend, softmax, top
from lab.taxonomy import ROOT
from lab.types import Decision, Option, Timer

NARROW = 10  # até 10 opções o decider renderiza "(A) texto" como string; acima disso, um token de rótulo por opção


class DeciderLlamaBackend(Backend):
    kind = "decision-model"

    def __init__(self, name: str, model: str, url: str, tokenizer: str, port: int | None = None,
                 temperature: float = 1.03, prefix_cache: str = "slot", n_probs: int = 256,
                 max_state_tokens: int = 1536, **kw: Any) -> None:
        super().__init__(name, model, **kw)
        if prefix_cache not in ("none", "slot", "restore"):
            raise ValueError(f"prefix_cache inválido: {prefix_cache}")
        from tokenizers import Tokenizer
        folder = Path(tokenizer) if Path(tokenizer).is_absolute() else ROOT / tokenizer
        self.tok = Tokenizer.from_file(str(folder / "tokenizer.json"))
        self.url, self.port = url.rstrip("/"), port
        self.temperature, self.prefix_cache, self.n_probs = temperature, prefix_cache, n_probs
        self.max_state_tokens = max_state_tokens
        self.client = httpx.Client(timeout=300)
        self._prefixes: dict[tuple, list[int]] = {}
        self._saved: set[str] = set()
        self._labels: list[int] | None = None

    def enc(self, text: str) -> list[int]:
        return self.tok.encode(text, add_special_tokens=False).ids

    def label_ids(self) -> list[int]:
        """A..Z e depois as strings de duas maiúsculas que são um token só (como decider.prompt.label_table)."""
        if self._labels is None:
            upper = string.ascii_uppercase
            names = list(upper) + [a + b for a in upper for b in upper]
            self._labels = [ids[0] for ids in map(self.enc, names) if len(ids) == 1][:255]
        return self._labels

    def prefix_ids(self, options: list[Option], question: str) -> list[int]:
        key = (question, tuple((o.key, o.description) for o in options))
        if key not in self._prefixes:
            texts = [f"{o.key}: {o.description}" if o.description else o.key for o in options]
            ids = self.enc(f"Question: {question}\nOptions:")
            if len(options) <= NARROW:
                ids += self.enc("".join(f"\n({string.ascii_uppercase[j]}) {t}" for j, t in enumerate(texts)))
            else:
                labels = self.label_ids()
                for j, t in enumerate(texts):
                    ids += self.enc("\n(") + [labels[j]] + self.enc(f") {t}")
            self._prefixes[key] = ids
        return self._prefixes[key]

    def _completion(self, ids: list[int], n_predict: int, cache: bool) -> dict[str, Any]:
        body = {"prompt": ids, "n_predict": n_predict, "n_probs": self.n_probs, "temperature": 0,
                "post_sampling_probs": False, "cache_prompt": cache, "id_slot": 0}
        response = self.client.post(f"{self.url}/completion", json=body)
        if response.status_code != 200:
            raise RuntimeError(f"{self.name}: HTTP {response.status_code}: {response.text[:300]}")
        return response.json()

    def _slot(self, action: str, filename: str) -> dict[str, Any]:
        response = self.client.post(f"{self.url}/slots/0?action={action}", json={"filename": filename})
        if response.status_code != 200:
            raise RuntimeError(f"{self.name}: /slots {action}: HTTP {response.status_code}: {response.text[:300]}")
        return response.json()

    def _decide(self, text: str, options: list[Option], question: str) -> Decision:
        prefix = self.prefix_ids(options, question)
        suffix = self.enc("\n\nContext:\n") + self.enc(text)[:self.max_state_tokens] + self.enc("\n\nAnswer: (")
        meta: dict[str, Any] = {"prefix_tokens": len(prefix), "suffix_tokens": len(suffix)}
        filename = "decider-" + hashlib.sha1(repr(prefix).encode()).hexdigest()[:16] + ".bin"
        if self.prefix_cache == "restore" and filename not in self._saved:  # 1ª vez deste schema: calcula e salva
            self._completion(prefix, 0, cache=True)
            meta["saved"] = self._slot("save", filename).get("n_written")
            self._saved.add(filename)
        with Timer() as t:
            if self.prefix_cache == "restore":
                with Timer() as r:
                    self._slot("restore", filename)
                meta["restore_ms"] = round(r.ms, 2)
            data = self._completion(prefix + suffix, 1, cache=self.prefix_cache != "none")
        by_id = {p["id"]: p["logprob"] for p in data["completion_probabilities"][0]["top_logprobs"]}
        labels = self.label_ids()[:len(options)]
        floor = min(by_id.values()) - 1.0  # letra fora do top-k: limite superior conservador
        logits = {o.key: by_id.get(i, floor) for i, o in zip(labels, options)}
        probs = softmax(logits, self.temperature)
        choice, confidence = top(probs)
        timings = data.get("timings", {})
        meta.update({"prompt_tokens_processed": timings.get("prompt_n"), "prompt_ms": timings.get("prompt_ms"),
                     "tokens_cached": data.get("tokens_cached"),
                     "letters_missing": [o.key for i, o in zip(labels, options) if i not in by_id]})
        return Decision(choice, confidence, probs, "probability", t.ms, self.name, self.model, meta)
