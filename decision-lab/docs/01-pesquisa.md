# Etapa 1 — Pesquisa: modelos e projetos para um "semantic decision router" local

Data da pesquisa: **3 de outubro de 2026**. O ecossistema é muito novo: o Jev (TypeSafe) entrou em early
access em 15/09/2026 e quase todas as alternativas abertas abaixo surgiram nas duas semanas seguintes.
Números de latência marcados com **(medido aqui)** vêm deste laboratório (VM com 4 vCPUs Xeon @ 2,8 GHz,
AVX-512, 15 GB de RAM, **sem GPU**); os demais são dos autores, quase sempre em GPU.

## O conceito

Um **modelo de decisão** ("System 1") lê um *estado* (texto) e uma lista de *opções descritas em
linguagem natural*, e devolve **uma probabilidade por opção em um único forward pass**, sem gerar texto.
O formato de requisição que virou padrão de fato é o do Jev (`POST /v1/systemone`): `state` + `questions`
com tipos `choice`, `noul` (sim/não) e `score` (escala).

Por dentro, as implementações abertas usam três arquiteturas:

| Arquitetura | Como lê a decisão | Exemplos |
|---|---|---|
| Decoder (LLM) + readout de letras | prompt lista as opções como A, B, C…; lê os logits do próximo token restritos às letras; softmax com temperatura calibrada | Jeff, decider, OpenJev, lev |
| Decoder + produto escalar de estados ocultos | último token vs. token final de cada opção | Kev-4B |
| Encoder bidirecional + cabeça de decisão | um marcador por opção, cabeça treinada pontua cada uma | Laya, Julia-1 |

Constatação importante ao ler o código do Jeff: o *readout* é uma camada linear inicializada a partir das
linhas do `lm_head` correspondentes às letras. Ou seja, estruturalmente é **"um LLM pontuado pelo logprob
da letra da opção"**, com três diferenças: (1) fine-tuning massivo em dados de decisão (~285 mil questões),
(2) um único forward sem amostragem, (3) temperatura ajustada para calibração. Isso permite um **controle
experimental limpo**: o Qwen3.5-0.8B original com exatamente o mesmo prompt e o mesmo readout
(backend `qwen3.5-0.8b-logprob` no laboratório) isola o efeito da especialização.

## Opções encontradas

### Modelos especializados em decisão (abertos)

| Projeto | Modelo-base | Parâmetros | Licença | Execução local / runtime | Fine-tuning / LoRA | Scores | Latência publicada | Idiomas | Observações |
|---|---|---|---|---|---|---|---|---|---|
| **Jeff** ([firelex/jeff](https://github.com/firelex/jeff), [HF](https://huggingface.co/mstrasser)) | Qwen3.5-0.8B / 2B, Gemma 4 E2B | 0,8B / 2B / 2B ef. (4,6B) | código MIT, pesos Apache-2.0 | `jeff-serve` (PyTorch, MLX); API `/v1/systemone` | sim: full e **LoRA** (adapter kit, 9 adapters oficiais de ~41 MB) | probabilidades calibradas (temperatura) | 22 ms (RTX PRO 6000), 28 ms (M4 Max), 463 ms (CPU 32 threads); **~3 s (medido aqui, 4 vCPU)** | oficialmente só inglês | lançado 28/09/2026; até 254 opções; layout *state-first* não permite cache de prefixo no modelo base |
| **decider** ([Mapika/decider](https://github.com/Mapika/decider)) | Qwen3.5-0.8B/2B/4B/35B-A3B Base | 0,8B–35B | Apache-2.0 | `decider.serve` (`/v1/systemone`), PyTorch, GGUF via llama-cpp-python, vLLM | receita de treino publicada | calibradas (ECE 0,03 in-task) | 4 ms (2B, GPU, CUDA graphs) | inglês | **cache de schema**: com as opções primeiro, o prefixo é computado uma vez — chave para CPU |
| **Julia-1** ([SupersonicLabs](https://huggingface.co/SupersonicLabs/Julia-1)) | mmBERT-small (encoder) | 144M | Apache-2.0 | PyTorch, ONNX/WebGPU, **llama.cpp** (GGUF) | não documentado | probabilidades | 3 ms (GPU); **~180 ms (medido aqui)** | 50+ (86% MASSIVE pt-PT) | 2–20 opções por chamada nativa |
| **Laya** ([NandhaKishorM/laya](https://github.com/NandhaKishorM/laya)) | ModernBERT-large / mmBERT-base | 421M / 322M | Apache-2.0 | `pip install laya`, `laya-serve`, ONNX, **llama.cpp** (só o EN) | notebooks (RLCD), checkpoint *typed-decisions* | calibradas, abstenção | 33 ms (T4); **~1,1 s (medido aqui, EN)** | EN; *laya-multilingual* 100+ | o GGUF multilíngue da comunidade não é reconhecido pelo llama.cpp atual |
| **Kev-4B**, **lev**, **Nimble-9B** | Qwen3.5-4B / 9B | 4–9B | variadas (abertas) | llama.cpp | — | probabilidades | 12–36 ms (GPU) | inglês | grandes demais para decisões rápidas em CPU |
| **OpenJev** ([openjev](https://huggingface.co/openjev/openjev)), APUS-OpenJev 4B/9B | Qwen3.8-27B (+ variantes) | 4–27B | aberta | llama.cpp (GGUF), MLX, FP8 | — | probabilidades | 43 ms (27B, GPU) | 6 idiomas | visão; fora do alcance de uma CPU doméstica no 27B |
| **Clef** (Cloudflare) | Qwen3.8-27B congelado + "joint schema head" | 27B | aberta | llama.cpp (em integração) | — | probabilidades | — | — | decide todas as perguntas conjuntamente |

### Hospedado (não local)

| Projeto | Disponibilidade | Custo | Latência | Por que não é o foco |
|---|---|---|---|---|
| **Jev** (TypeSafe) | só API (TypeSafe, OpenRouter); sem pesos, sem paper | US$ 0,042 / milhão de tokens de entrada | 114–212 ms por chamada incl. rede | não roda localmente; o laboratório tem o backend pronto (`systemone` com `api_key_env`) para comparar quando houver credencial |

### Runtimes / servidores

| Runtime | O que faz | Status aqui |
|---|---|---|
| **llama.cpp `llama-server`** | suporte nativo a modelos de decisão (`/v1/systemone`): tipos laya, openjev, lev, kev, nimble, clef; quantização GGUF; CPU otimizada | **usado** (Julia-1, Laya, e os LLMs generativos) |
| `jeff-serve` | servidor oficial do Jeff (PyTorch/MLX) com adapters LoRA | **usado** |
| `decider.serve` | servidor do decider com cache de schema | testado no experimento de cache |
| ollaya | "Ollama para modelos de decisão" (Laya, decider, NLI, GLiClass…) | não usado (exige glibc ≥ 2.38; o llama.cpp cobre o mesmo papel) |
| laya-serve | servidor do Laya | não usado |

### Alternativas tradicionais (para comparação)

| Abordagem | Modelo usado aqui | Parâmetros | Classes dinâmicas? | Observação |
|---|---|---|---|---|
| Zero-shot NLI | mDeBERTa-v3-base-xnli (MIT) | 280M | sim | 1 forward **por opção** — custo cresce linearmente com o nº de classes |
| Zero-shot GLiClass | gliclass-multilang-edge (Apache-2.0) | ~140M | sim | 1 forward, sigmoides independentes por rótulo |
| Similaridade de embedding (zero-shot) | multilingual-e5-small (MIT) | 118M | sim | fala vs. descrição da opção |
| "Semantic router" (aurelio) | e5-small + frases-exemplo por rota (kNN) | 118M | não (precisa de exemplos) | o padrão mais citado para roteamento rápido |
| Classificador treinado | TF-IDF + regressão logística; e5 + regressão logística | — / 118M | não | precisa de dados rotulados |
| LLM pequeno genérico (logprob) | Qwen3.5-0.8B, mesmo prompt do Jeff | 0,8B | sim | controle experimental do Jeff |
| LLM generativo (JSON restrito) | Qwen3.5-0.8B / 2B / 4B, llama.cpp | 0,8–4B | sim | gera tokens; confiança = prob. do 1º token do rótulo |

### Atualização de 04/10/2026 (checagem rápida ao retomar na máquina local)

| Item | Estado | Efeito no laboratório |
|---|---|---|
| Jeff v1.3 / adapters novos | **ainda não saiu**: o README segue em v1.2 + 9 adapters, com o v1.3 "em ~36 horas" | nenhum; continua o v1.2 |
| decider-4b | **saiu** (v2.1), com GGUF oficial (Q4_K_M 2,7 GB, Q8_0, BF16); também há GGUF do 2B. **Não há GGUF do 0.8B** | o 0.8B foi convertido localmente para o experimento de prefixo no llama.cpp |
| Clef no llama.cpp | **entrou** (`conversion/clef.py`, tipo reconhecido pelo `server-decision.cpp`) | nenhum: a base de 27B não cabe nesta máquina |
| Laya multilíngue em GGUF | **não há GGUF compatível**: o da comunidade traz só o backbone; a cabeça de decisão fica num `.safetensors` à parte, fora do llama.cpp | nenhum |

Nenhuma decisão registrada abaixo mudou.

## Escolha para o laboratório

**Decisão: não escolher um modelo só. O laboratório fala o protocolo `/v1/systemone`** e trata qualquer
modelo de decisão como um backend configurável, ao lado de alternativas tradicionais com a mesma interface.
Justificativa: o ecossistema mudou de semana a semana durante a própria pesquisa (Jeff v1.3, Clef no
llama.cpp e decider-4b anunciados para os próximos dias); um laboratório preso a um modelo envelheceria
antes de terminar o experimento.

Modelos colocados em produção no laboratório e por quê:

1. **Jeff-Qwen3.5-0.8B v1.2** — é a referência pedida, o menor decoder especializado com pesos abertos,
   LoRA pronto e servidor próprio. Rodado no servidor oficial (PyTorch fp32 na CPU).
2. **Julia-1** — o menor (144M), multilíngue, roda no llama.cpp: o candidato natural para "rápido em CPU".
3. **Laya (EN)** — encoder de decisão de outra família, também no llama.cpp.
4. **decider-0.8b** — mesmo tamanho do Jeff, mas treinado também no layout *schema-first*: permite testar
   o cache de prefixo, a otimização mais promissora para CPU.
5. **Qwen3.5-0.8B / 2B / 4B** genéricos — controle (mesma base do Jeff) e "LLM convencional".
6. **NLI, GLiClass, e5 (zero-shot, kNN, regressão logística), TF-IDF** — alternativas tradicionais.

Ressalva registrada antes dos testes: Jeff, decider e Laya-EN se declaram **"English only"**, e o caso de
uso é em **português**. O laboratório testa os dois idiomas nas descrições das opções (`option_lang`).
