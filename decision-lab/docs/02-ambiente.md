# Etapa 2 — Ambiente

## Máquina usada

VM na nuvem, **sem GPU**: 4 vCPUs Intel Xeon @ 2,8 GHz (AVX2, AVX-512, AVX-512 VNNI, sem bf16 nativo),
15 GB de RAM, Linux, Python 3.12 (via uv). É uma máquina **mais fraca que um PC doméstico atual** —
referência medida com `llama-bench` (Qwen3.5-0.8B):

| quantização | threads | prefill (tok/s) | geração (tok/s) |
|---|---|---|---|
| Q8_0 | 4 | 122 | 17,5 |
| Q4_0 | 4 | 167 | 23,1 |
| Q8_0 | 2 | 79 | 11,0 |

Um desktop com 8–16 núcleos modernos deve ser ~3–6× mais rápido em CPU; qualquer GPU recente, 50–100×.
**Todas as latências deste laboratório devem ser lidas nessa escala.**

## O que foi instalado

| Componente | Versão | Onde | Para quê |
|---|---|---|---|
| Jeff (servidor oficial `jeff-serve`) | commit `d0173b4`, pesos v1.2 | `vendor/jeff/.venv` | modelo de decisão de referência |
| PyTorch CPU | 2.14 | venvs | Jeff, decider, modelos locais |
| transformers | 5.17 (Jeff) / 5.18 (lab) | venvs | |
| llama.cpp | commit `836d571` (03/10/2026), build nativo CPU | `vendor/llama.cpp/build` | Julia-1, Laya, Qwen3.5 0.8B/2B/4B; endpoint `/v1/systemone` |
| decider | `main` | `vendor/decider/.venv` | experimento de cache de schema |
| laboratório (FastAPI, scikit-learn, sentence-transformers, gliclass) | ver `requirements.txt` | `.venv` | API, baselines, benchmarks |

Modelos (≈9 GB em `models/`): Jeff-Qwen3.5-0.8B v1.2 (1,7 GB fp32 em disco, ~3,9 GB de RSS servindo),
decider-0.8b, Julia-1 Q8_0 (168 MB), Laya Q8_0 (449 MB), Qwen3.5-0.8B Q8_0, Qwen3.5-2B Q4_K_M,
Qwen3.5-4B Q4_K_M, multilingual-e5-small, mDeBERTa-v3-base-xnli, gliclass-multilang-edge.

Todos os comandos estão em [scripts/setup.sh](../scripts/setup.sh) (idempotente).

## Processos

| Porta | Processo | Modelo |
|---|---|---|
| 8765 | `jeff-serve` (PyTorch fp32) | Jeff-Qwen3.5-0.8B v1.2 |
| 8811 / 8812 | `llama-server` (decisão) | Julia-1 / Laya |
| 8801 / 8802 / 8803 | `llama-server` | Qwen3.5-0.8B / 2B / 4B |
| 8000 | `uvicorn lab.server:app` | API do laboratório (+ backends locais carregados sob demanda) |

`scripts/services.sh start|stop|status` gerencia os servidores de modelos.

## Arquitetura do harness

- **Uma interface** (`Backend.decide(text, options, question) -> Decision`) para todos os motores.
  `Decision` = `decision`, `confidence`, `scores`, `score_kind`, `latency_ms`, `backend`, `model`,
  `metadata`. O campo `score_kind` deixa explícito o que a confiança significa (`probability` calibrada,
  `pseudo_probability`, `similarity`, `token_probability`) — misturar esses significados é a armadilha
  mais comum ao definir limiares.
- **Protocolo System One** como cidadão de primeira classe: qualquer modelo de decisão novo que fale
  `/v1/systemone` entra no laboratório com 5 linhas de YAML.
- **Política de roteamento separada do modelo** (`lab/router.py`): o modelo diz o que a fala é; a política
  decide o que fazer com base na confiança (ignorar, perguntar ou escalar).
- **Log estruturado** de toda decisão (`runs/decisions.jsonl`) e **eventos SSE** para a UI.

## Problemas encontrados (e soluções)

1. **O lock do Jeff instala o torch CUDA do PyPI** (~3 GB de bibliotecas NVIDIA inúteis numa máquina sem GPU).
   Instalei as mesmas versões fixadas, com o wheel CPU de `download.pytorch.org`.
2. **uv antigo**: o Jeff exige uv ≥ 0.12.19; `uv self update` falhou por rate-limit da API do GitHub.
   Instalado via `pip install --user -U "uv>=0.12.19"`.
3. **CLI `hf` com vários padrões em um `--include/--exclude`** só considera o primeiro: downloads
   incompletos (sem `config.json`). Solução: repetir a flag.
4. **mDeBERTa carregou em float16 na CPU** (dtype gravado no config) — 5× mais lento. Forçado fp32.
   GLiClass carregou em bf16 e quebrou (`mat1 and mat2 must have the same dtype`). Forçado fp32.
5. **Qwen3.5 (base do Jeff/decider) usa atenção linear Gated DeltaNet**, que no transformers só tem kernel
   rápido em GPU (`flash-linear-attention`). Na CPU cai num fallback em PyTorch puro: ~30% do tempo do Jeff
   (perfil: `linalg_solve_triangular`, `conv1d`). Quantização int8 dinâmica do torch só reduziu de 2,0 s para
   1,6 s. O llama.cpp tem kernels CPU nativos para essa arquitetura.
6. **OOM com vários `llama-server`**: o llama-server atual mantém por padrão um cache de prompts em RAM de
   até 8 GB por processo, e no Qwen3.5 ele guarda checkpoints de estado recorrente. O servidor do 0.8B
   chegou a 5,6 GB e foi morto pelo OOM killer no meio do benchmark. Solução: `--cache-ram 0` (também é o
   correto para medir latência sem reaproveitamento entre requisições).
7. **GGUF comunitário do Laya multilíngue** não é reconhecido como modelo de decisão pelo llama.cpp atual
   (HTTP 501) — foi convertido antes do suporte oficial. Só o Laya EN (ggml-org) foi usado.
8. **`jeff-serve` atende uma requisição por vez** e devolve 529 para concorrentes. O cliente do laboratório
   agora faz retry curto em 529/503.
9. `pkill -f <padrão>` matava o próprio shell (o padrão aparece na linha de comando). Usado `pkill -f "[l]lama-server"`.

---

# Máquina local (retomada em 04/10/2026)

## Hardware detectado

| Item | Valor |
|---|---|
| SO | Windows 11 Pro 10.0.22000 (x64); laboratório dentro do **WSL2** (Ubuntu 24.04.2, kernel 6.18, glibc 2.39) |
| CPU | Intel Core i5-9400F @ 2,9 GHz — **6 núcleos / 6 threads**, AVX2 + FMA + F16C, **sem AVX-512** |
| RAM | 15,9 GB no host (≈ 7 GB livres com o uso normal do desktop); WSL2 configurado para 12 GB + 8 GB de swap |
| GPU | AMD Radeon RX 580 (Polaris, driver 31.0.21923). **Sem NVIDIA/CUDA, sem Apple Silicon/MLX** |
| Disco | 178 GB livres em C:; dados pesados no ext4 do WSL (`~/decision-lab-data`) |

Consequência: a máquina cai no **caminho CPU**. A RX 580 não serve para PyTorch (sem CUDA; ROCm não suporta
Polaris; não há `flash-linear-attention` fora de CUDA), então o Jeff/decider em PyTorch e o treino de LoRA
continuam em CPU. Ela só poderia ajudar via llama.cpp + Vulkan (ver "Próximos passos").

## Escolhas e justificativas

1. **WSL2 em vez de Windows nativo** — os scripts são bash, o Jeff/decider só são testados em Linux/macOS, e o
   build nativo do llama.cpp é trivial no Ubuntu.
2. **Repositório em `C:\projeto\assistant` (NTFS), dados pesados no ext4 do WSL.** `vendor/`, `models/` e
   `.venv` são symlinks para `~/decision-lab-data` (`LAB_DATA=... scripts/setup.sh`). Motivo: o DrvFs
   (`/mnt/c`) é lento demais para venvs (dezenas de milhares de arquivos) e para carregar ~9 GB de modelos.
3. **`.wslconfig` com `memory=12GB`, `swap=8GB`** (o arquivo não existia; o padrão do WSL2 é 50% da RAM =
   8 GB). Motivo: o pipeline precisa de decider (3,5 GB) + Qwen 2B (1,6 GB) + Qwen 4B (4,4 GB) + lab ao mesmo
   tempo. Não cabe "tudo de uma vez" (Jeff + decider + 3 LLMs ≈ 15 GB): os serviços são subidos por grupo,
   conforme o benchmark.
4. **Toolchain**: `apt-get install build-essential cmake ninja-build pkg-config` (via `wsl -u root`, pois o
   `sudo` do usuário pede senha); `uv 0.12.23` pelo instalador oficial (≥ 0.12.19 exigido pelo Jeff).
5. **`.gitattributes` com `eol=lf`** em `decision-lab/`: o Git for Windows (`core.autocrlf=true`) fazia
   checkout dos `.sh` com CRLF, o que quebra o bash do WSL.

## Mudanças no `scripts/setup.sh`

- `ACCEL=auto|cpu|cuda|mlx` (auto: `nvidia-smi` → cuda; Darwin arm64 → mlx; senão cpu).
  - `cuda`: torch do índice CUDA, Jeff com `uv sync --extra cuda`, llama.cpp com `-DGGML_CUDA=ON`, decider com
    `flash-linear-attention`.
  - `mlx`: Jeff com `uv sync --extra mac` (servir com `JEFF_BACKEND=mlx`), llama.cpp com Metal (padrão no macOS).
  - `cpu`: igual ao que rodou na nuvem (wheels CPU, mesmas versões fixadas).
  - **Só o caminho `cpu` foi executado e validado** (nesta máquina e na VM). `cuda` e `mlx` foram escritos a
    partir da documentação dos projetos e não puderam ser testados aqui.
- `LAB_DATA=/caminho`: coloca `vendor/`, `models/` e `.venv` fora do repositório, com symlinks.
- Checagem explícita de `uv >= 0.12.19`.

Comando usado:

```bash
LAB_DATA=$HOME/decision-lab-data bash scripts/setup.sh
```
