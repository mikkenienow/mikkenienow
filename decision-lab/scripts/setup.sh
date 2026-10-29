#!/usr/bin/env bash
# Prepara o laboratório do zero. Idempotente: pode rodar de novo.
# Plataformas: Linux x86-64 (CPU ou NVIDIA/CUDA), macOS Apple Silicon (MLX/Metal), Windows via WSL2.
# Requisitos: git, cmake, g++, curl e uv >= 0.12.19 (curl -LsSf https://astral.sh/uv/install.sh | sh).
# Espaço: ~12 GB (modelos ~9 GB). RAM: 16 GB para subir tudo ao mesmo tempo.
#
# Variáveis:
#   ACCEL=auto|cpu|cuda|mlx   acelerador (padrão: auto — cuda se houver nvidia-smi, mlx em Apple Silicon, senão cpu)
#   LAB_DATA=/caminho         onde ficam vendor/, models/ e .venv (viram symlinks no repositório).
#                             Use no WSL2 quando o repositório está em /mnt/c: o DrvFs é lento demais
#                             para venvs e para carregar modelos. Ex.: LAB_DATA=$HOME/decision-lab-data
set -euo pipefail
cd "$(dirname "$0")/.."
LAB=$PWD

# ---- uv >= 0.12.19 (exigido pelo vendor/jeff)
command -v uv >/dev/null || { echo "uv não encontrado (curl -LsSf https://astral.sh/uv/install.sh | sh)"; exit 1; }
UV_VER=$(uv --version | awk '{print $2}')
if [ "$(printf '%s\n' 0.12.19 "$UV_VER" | sort -V | head -1)" != 0.12.19 ]; then
  echo "uv $UV_VER é antigo: o Jeff exige >= 0.12.19"; exit 1
fi

# ---- acelerador
ACCEL=${ACCEL:-auto}
if [ "$ACCEL" = auto ]; then
  if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then ACCEL=cuda
  elif [ "$(uname -s)" = Darwin ] && [ "$(uname -m)" = arm64 ]; then ACCEL=mlx
  else ACCEL=cpu; fi
fi
case $ACCEL in
  cuda) TORCH_INDEX=${TORCH_INDEX:-https://download.pytorch.org/whl/cu128}; LLAMA_FLAGS="-DGGML_CUDA=ON" ;;
  mlx)  TORCH_INDEX="";                                                     LLAMA_FLAGS="" ;;  # Metal é o padrão no macOS
  cpu)  TORCH_INDEX=https://download.pytorch.org/whl/cpu;                   LLAMA_FLAGS="" ;;
  *) echo "ACCEL desconhecido: $ACCEL"; exit 1 ;;
esac
echo "== acelerador: $ACCEL"
NPROC=$(nproc 2>/dev/null || sysctl -n hw.ncpu)
torch_install() {  # python, pacotes...
  local py=$1; shift
  if [ -n "$TORCH_INDEX" ]; then uv pip install -q --python "$py" "$@" --index-url "$TORCH_INDEX"
  else uv pip install -q --python "$py" "$@"; fi
}

# ---- diretórios pesados (opcionalmente fora do repositório)
for d in vendor models .venv; do
  if [ -n "${LAB_DATA:-}" ] && [ ! -e "$d" ]; then mkdir -p "$LAB_DATA/$d"; ln -s "$LAB_DATA/$d" "$d"; fi
done
mkdir -p vendor models/gguf models/hf runs/logs

echo "== 1. venv do laboratório (Python 3.12, torch $ACCEL)"
[ -x .venv/bin/python ] || uv venv --allow-existing --python 3.12 .venv
torch_install .venv/bin/python torch
uv pip install -q --python .venv/bin/python -r requirements.txt

echo "== 2. Jeff (servidor oficial; mesmas versões fixadas do projeto)"
[ -d vendor/jeff ] || git clone --depth 1 https://github.com/firelex/jeff.git vendor/jeff
(cd vendor/jeff
 case $ACCEL in
   cuda) uv sync --extra cuda ;;   # lock oficial: torch CUDA do PyPI
   mlx)  uv sync --extra mac ;;    # servir com JEFF_BACKEND=mlx
   cpu)  # o lock instalaria o torch CUDA (~3 GB de libs NVIDIA inúteis): mesmas versões, wheel CPU
     [ -x .venv/bin/python ] || uv venv --python 3.12 .venv
     torch_install .venv/bin/python torch==2.14.0 torchvision==0.29.0
     uv pip install -q --python .venv/bin/python "transformers==5.17.0" "pillow==12.3.0" "fastapi==0.141.1" "uvicorn==0.52.4" \
       "safetensors==0.8.0" "numpy==2.5.3" "huggingface-hub==1.31.0" "peft==0.21.1" httpx
     uv pip install -q --python .venv/bin/python --no-deps -e . ;;
 esac)
HF=vendor/jeff/.venv/bin/hf

echo "== 3. llama.cpp (build nativo; $ACCEL)"
[ -d vendor/llama.cpp ] || git clone --depth 1 https://github.com/ggml-org/llama.cpp.git vendor/llama.cpp
(cd vendor/llama.cpp
 # shellcheck disable=SC2086
 cmake -B build -DGGML_NATIVE=ON -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF -DCMAKE_BUILD_TYPE=Release $LLAMA_FLAGS > /dev/null
 cmake --build build -j"$NPROC" --target llama-server llama-bench > /dev/null)

echo "== 4. decider (cache de schema)"
[ -d vendor/decider ] || git clone --depth 1 https://github.com/Mapika/decider.git vendor/decider
(cd vendor/decider
 [ -x .venv/bin/python ] || uv venv --python 3.12 .venv
 torch_install .venv/bin/python torch
 uv pip install -q --python .venv/bin/python "transformers>=5" numpy huggingface_hub jinja2 fastapi uvicorn httpx
 # kernel rápido do Gated DeltaNet: só existe para GPU
 if [ "$ACCEL" = cuda ]; then uv pip install -q --python .venv/bin/python flash-linear-attention; fi
 uv pip install -q --python .venv/bin/python --no-deps -e .)

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
