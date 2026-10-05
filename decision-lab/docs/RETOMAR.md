# Prompt para retomar o trabalho localmente

Cole o bloco abaixo no Claude Code, aberto na pasta do repositório clonado na sua máquina.

---

```text
Estou retomando, na minha máquina local, um experimento de "semantic decision router" que começou numa
sessão na nuvem. O código está no repositório mikkenienow/mikkenienow, branch
claude/semantic-decision-router-5n40in, pasta decision-lab/. Faça checkout dessa branch se ainda não estiver nela.

ANTES DE QUALQUER COISA, leia nesta ordem:
- decision-lab/README.md
- decision-lab/docs/01-pesquisa.md
- decision-lab/docs/02-ambiente.md
- decision-lab/docs/03-resultados.md
- decision-lab/runs/bench/REPORT.md
Não refaça a pesquisa nem re-litigue decisões já registradas ali, a menos que algo tenha mudado de fato
(o ecossistema de modelos de decisão muda toda semana: vale checar rapidamente se saíram Jeff v1.3 e
adapters novos, decider-4b novo, Clef no llama.cpp, ou um Laya multilíngue em GGUF compatível).

CONTEXTO (resumo do que já existe):
- O laboratório tem backends plugáveis com a interface Backend.decide(text, options, question) -> Decision
  e usa o protocolo /v1/systemone (formato do Jev). Os modelos testados foram Jeff-0.8B, decider-0.8b
  (com cache de schema), Julia-1, Laya, Qwen3.5 0.8B/2B/4B (logprob e geração de JSON), NLI, GLiClass,
  embeddings e TF-IDF.
- Há uma API FastAPI (lab/server.py) com /v1/decide, /v1/route, log JSONL, SSE e uma UI.
  Executores simulados (casa, mídia, timers) e um LLM local respondem as rotas LLM.
- Benchmarks: bench/run_bench.py, scaling.py, cascade.py, pipeline.py e report.py.
  O dataset em PT-BR (159 testes + 64 de treino) é gerado por data/build_dataset.py.
- Tudo foi medido numa VM de 4 vCPUs SEM GPU. A conclusão principal é que modelos de decisão
  zero-shot acertam bem a intenção (91–98%), mas não sabem dizer se a fala é dirigida ao assistente
  (38–45% de falsa ativação).
- A especialização vale +31 pontos (Qwen3.5-0.8B original → Jeff, com o mesmo prompt e o mesmo custo).
- Na CPU, o cache de schema do decider deu 5,6× de velocidade sobre o Jeff, com a mesma qualidade.
- O backend padrão é a cascata e5-logreg → decider-0.8b-schema (τ=0.3): 89% de acurácia,
  7,5% de falsa ativação e ~120 ms na VM.

PASSO 1 — AMBIENTE LOCAL
1. Detecte o hardware: SO, CPU (núcleos), RAM, GPU (NVIDIA/CUDA? Apple Silicon/MLX?).
   Registre isso em docs/02-ambiente.md, numa seção "Máquina local".
2. O scripts/setup.sh foi escrito para Linux x86-64 sem GPU. Adapte sem quebrar o caminho CPU:
   - NVIDIA: torch CUDA; Jeff com `--extra cuda`; llama.cpp com `-DGGML_CUDA=ON`; decider pode instalar
     flash-linear-attention.
   - Apple Silicon: Jeff com JEFF_BACKEND=mlx (`--extra mac`); llama.cpp com Metal.
   - Windows: prefira WSL2.
   Requisito: uv >= 0.12.19 (o vendor/jeff exige).
3. Os modelos (~9 GB) e vendor/ NÃO estão no git: rode o setup para baixar.
   O CLI `hf` aceita UM padrão por --include, então repita a flag.
4. Mantenha `--cache-ram 0` nos llama-server (sem isso houve OOM).
   Em CPU, carregue modelos em fp32 (alguns configs vêm em fp16/bf16 e ficam 5× mais lentos).
5. Suba tudo (scripts/services.sh start all; decider: veja o comando em docs/02-ambiente.md, porta 8821
   com DECIDER_SCHEMA_CACHE=1) e depois scripts/lab.sh. Valide com o smoke test da API (exemplos no README).

PASSO 2 — REMEDIR NA MÁQUINA LOCAL
Rode de novo, com --perturb, pelo menos: jeff-0.8b, jeff-0.8b-pt, decider-0.8b-schema, e5-logreg,
qwen3.5-0.8b-logprob, qwen3.5-4b-chat. Rode também o bench.pipeline e o bench.scaling.
Salve os resultados separados dos da nuvem (por exemplo, runs/bench-local/, parametrizando o diretório
de saída) para comparar as duas máquinas. Com GPU, verifique se o Jeff chega perto dos ~22–30 ms
publicados. Atualize docs/03-resultados.md com uma seção "Máquina local" e diga explicitamente o que
mudou nas conclusões. Execute os benchmarks um backend por vez, sem outro trabalho pesado em paralelo.

PASSO 3 — PRÓXIMO EXPERIMENTO PRIORITÁRIO (se houver GPU)
Fine-tuning de domínio focado em "a fala é dirigida ao assistente?":
- Gere ~1–2 mil exemplos em PT-BR no formato do adapter kit do Jeff (vendor/jeff/examples/adapter-kit),
  com variações de destinatário: narrativas sobre dispositivos, pedidos a outras pessoas, TV ao fundo,
  menções à Alexa sem pedido, nomes parecidos. Siga as checagens de vazamento e de atalhos do kit.
  Mantenha o data/test.jsonl atual INTOCADO como teste; nenhuma frase do teste pode entrar no treino.
- Treine um LoRA (jeff-train --lora-rank 16) e sirva com JEFF_ADAPTERS.
  Compare com jeff-0.8b, e5-logreg e a cascata. Hipótese: falsa ativação < 10% sem precisar
  do classificador separado.
- Sem GPU, faça antes o experimento 2 de docs/03-resultados.md: decider/Jeff em GGUF no llama.cpp com o
  estado do prefixo salvo (/slots save/restore), para juntar os kernels de CPU com o cache de schema.

PASSO 4 — SÓ DEPOIS: FASE 3 (celular ↔ PC)
HOST=0.0.0.0 scripts/lab.sh e a UI aberta no navegador do celular. Meça a latência de rede somada à da
decisão. Fases 4 (voz contínua com whisper.cpp + VAD) e 5 (Alexa/automação) continuam bloqueadas até a
fase anterior estar estável. Não pule fases.

REGRAS DE TRABALHO
- Trabalhe de forma autônoma. Só me pergunte quando precisar de credencial, de hardware ou de uma decisão
  que não seja técnica. Registre cada escolha e a justificativa.
- A investigação é imparcial: não tente provar que o Jeff (ou qualquer modelo) é melhor.
- Ao fim de cada etapa, registre nos docs: o que instalou, os comandos usados, a arquitetura, os resultados,
  os problemas encontrados e os próximos experimentos.
- Faça commits pequenos na mesma branch e push ao terminar cada etapa.
```
