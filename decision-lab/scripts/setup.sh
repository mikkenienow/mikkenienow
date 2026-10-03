#!/usr/bin/env bash
# Prepara o laboratório do zero (Linux x86-64, CPU). Idempotente: pode rodar de novo.
# Requisitos: git, cmake, g++, curl e uv >= 0.12.19 (pip install --user -U "uv>=0.12.19").
# Espaço: ~12 GB (modelos ~9 GB). RAM: 16 GB para subir tudo ao mesmo tempo.
set -euo pipefail
cd "$(dirname "$0")/.."
LAB=$PWD
mkdir -p vendor models/gguf models/hf runs/logs

echo "== 1. venv do laboratório (Python 3.12, torch CPU)"
[ -d .venv ] || uv venv --python 3.12 .venv
uv pip install -q --python .venv/bin/python torch --index-url https://download.pytorch.org/whl/cpu
uv pip install -q --python .venv/bin/python -r requirements.txt

echo "== 2. Jeff (servidor oficial; mesmas versões fixadas do projeto, mas torch CPU em vez do build CUDA do PyPI)"
[ -d vendor/jeff ] || git clone --depth 1 https://github.com/firelex/jeff.git vendor/jeff
(cd vendor/jeff
 [ -d .venv ] || uv venv --python 3.12 .venv
 uv pip install -q --python .venv/bin/python torch==2.14.0 torchvision==0.29.0 --index-url https://download.pytorch.org/whl/cpu
 uv pip install -q --python .venv/bin/python "transformers==5.17.0" "pillow==12.3.0" "fastapi==0.141.1" "uvicorn==0.52.4" \
   "safetensors==0.8.0" "numpy==2.5.3" "huggingface-hub==1.31.0" "peft==0.21.1" httpx
 uv pip install -q --python .venv/bin/python --no-deps -e .)
HF=vendor/jeff/.venv/bin/hf

echo "== 3. llama.cpp (CPU nativo: AVX2/AVX-512 detectados no build)"
[ -d vendor/llama.cpp ] || git clone --depth 1 https://github.com/ggml-org/llama.cpp.git vendor/llama.cpp
(cd vendor/llama.cpp
 cmake -B build -DGGML_NATIVE=ON -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF -DCMAKE_BUILD_TYPE=Release > /dev/null
 cmake --build build -j"$(nproc)" --target llama-server llama-bench > /dev/null)

echo "== 4. decider (para o experimento de cache de schema)"
[ -d vendor/decider ] || git clone --depth 1 https://github.com/Mapika/decider.git vendor/decider
(cd vendor/decider
 [ -d .venv ] || uv venv --python 3.12 .venv
 uv pip install -q --python .venv/bin/python torch --index-url https://download.pytorch.org/whl/cpu
 uv pip install -q --python .venv/bin/python "transformers>=5" numpy huggingface_hub jinja2 fastapi uvicorn httpx
 uv pip install -q --python .venv/bin/python --no-deps -e .)  # sem flash-linear-attention (só GPU)

echo "== 5. Modelos"
# Obs.: o CLI hf aceita UM padrão por --include; repita a flag para vários.
$HF download mstrasser/Jeff-Qwen3.5-0.8B --revision v1.2 --local-dir models/Jeff-Qwen3.5-0.8B-v1.2 --exclude "videos/*"
$HF download Mapika/decider-0.8b --local-dir models/decider-0.8b
$HF download ggml-org/Julia-1-GGUF Julia-1-Q8_0.gguf --local-dir models/gguf
$HF download ggml-org/Laya-GGUF Laya-Q8_0.gguf --local-dir models/gguf
$HF download ggml-org/Qwen3.5-0.8B-GGUF Qwen3.5-0.8B-Q8_0.gguf --local-dir models/gguf
$HF download unsloth/Qwen3.5-2B-GGUF Qwen3.5-2B-Q4_K_M.gguf --local-dir models/gguf
$HF download unsloth/Qwen3.5-4B-GGUF Qwen3.5-4B-Q4_K_M.gguf --local-dir models/gguf
for m in intfloat/multilingual-e5-small MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7 knowledgator/gliclass-multilang-edge; do
  $HF download "$m" --local-dir "models/hf/$(basename "$m")" --include "*.json" --include "*.safetensors" \
    --include "*.model" --include "*.txt" --include "1_Pooling/*"
done

echo "== 6. Dataset"
.venv/bin/python data/build_dataset.py

echo "pronto. Próximo: scripts/services.sh start all && scripts/lab.sh"
