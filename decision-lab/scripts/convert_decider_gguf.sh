#!/usr/bin/env bash
# Converte o decider-0.8b (safetensors) para GGUF. O projeto só publica GGUF do 2B e do 4B.
#   scripts/convert_decider_gguf.sh [q8_0|f16|bf16|f32]     (padrão: q8_0)
# O decider lê a decisão nos logits das letras no LM head, então o GGUF comum de texto basta: não há cabeça extra.
set -euo pipefail
cd "$(dirname "$0")/.."
TYPE=${1:-q8_0}
OUT=models/gguf/decider-0.8b-${TYPE^^}.gguf
PY=vendor/decider/.venv/bin/python   # já tem torch + transformers
uv pip install -q --python "$PY" vendor/llama.cpp/gguf-py sentencepiece protobuf
# --no-mtp: o config.json herda "mtp_num_hidden_layers": 1 do Qwen3.5 base, mas o checkpoint fine-tunado não traz
# os pesos da camada MTP; sem a flag o GGUF declara 25 blocos e o llama.cpp falha ("blk.24.attn_norm.weight not found").
"$PY" vendor/llama.cpp/convert_hf_to_gguf.py models/decider-0.8b --outfile "$OUT" --outtype "$TYPE" --no-mtp 2>&1 \
  | grep -E "^(INFO:hf-to-gguf:Model|Traceback|[A-Za-z]*Error|usage:)" || true
ls -la "$OUT"
