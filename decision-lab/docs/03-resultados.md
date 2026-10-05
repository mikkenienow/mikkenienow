# Etapas 3–7 — Resultados

Tudo medido em 3–4/10/2026 numa VM **sem GPU, com 4 vCPUs** (ver [02-ambiente.md](02-ambiente.md)).
Latências absolutas são piores que num PC doméstico; as **razões** entre abordagens são o que importa.
Tabelas completas: [runs/bench/REPORT.md](../runs/bench/REPORT.md). Predições item a item: `runs/bench/<backend>/`.

## Como foi medido

- **Dataset** ([data/build_dataset.py](../data/build_dataset.py)): 159 falas em PT-BR para teste — 58 *não*
  destinadas ao assistente (conversa, TV, pedidos a outra pessoa, menções à Alexa sem pedido, nomes parecidos,
  erros de transcrição) e 101 destinadas, em 5 intenções (`home_control`, `media`, `timer_alarm`, `knowledge`,
  `complex`). 11 itens ambíguos aceitam mais de uma resposta. 64 exemplos de treino **separados** (sem
  sobreposição) só para os baselines treináveis. O dataset foi escrito por mim (Claude) para este experimento:
  é pequeno e tem o viés de quem escreveu; serve para comparar abordagens entre si, não para estimar acurácia
  em produção.
- **Métricas**: acurácia (aceitando as respostas válidas dos ambíguos); **falsa ativação** = fração das falas
  não destinadas em que o assistente "acordou"; **pedidos perdidos** = fração das destinadas que foram ignoradas;
  acerto de intenção quando ativou; latência p50/p95 de parede (uma requisição por vez, como num fluxo de voz);
  **CPU-segundos por decisão** (processo do modelo + do laboratório); ECE (calibração) e AUROC da confiança
  (a confiança separa acertos de erros?); estabilidade = mesma decisão para a fala sem acentos/pontuação.
- **Execução sequencial**, um backend por vez, 2 aquecimentos antes; nenhum outro trabalho pesado em paralelo.

## Resultado principal

| backend | grupo | acurácia | falsa ativação | perdidos | intenção | p50 | CPU-s | ECE | AUROC |
|---|---|---|---|---|---|---|---|---|---|
| `e5-logreg` | B) treinado (64 ex.) | **86,8%** | **11,3%** | 2,0% | 86,6% | **27 ms** | **0,11** | 0,42 | **0,89** |
| `tfidf-logreg` | B) treinado | 78,0% | 30,2% | 6,1% | 86,0% | 2 ms | 0,004 | 0,19 | 0,80 |
| `e5-knn-router` | B) "semantic router" | 73,0% | 60,4% | 0,0% | 88,9% | 26 ms | 0,10 | – | 0,71 |
| `jeff-0.8b` (opções EN) | C) decisão | 79,2% | 45,3% | 4,0% | 94,7% | 3 051 ms | 7,3 | 0,10 | 0,75 |
| `jeff-0.8b-pt` (opções PT) | C) decisão | 82,4% | 37,7% | 2,0% | 93,8% | 3 072 ms | 7,5 | 0,16 | 0,70 |
| `jeff-0.8b-gate` (+ pergunta noul) | C) decisão | 79,9% | 17,0% | 21,2% | 97,4% | 5 124 ms | 12,6 | 0,15 | 0,71 |
| `decider-0.8b-schema` | C) decisão + cache | 78,6% | 37,7% | 6,1% | 91,4% | **542 ms** | 2,2 | **0,02** | 0,81 |
| `julia-1` | C) decisão (144M) | 34,6% | 100% | 0,0% | 53,5% | 177 ms | 0,8 | 0,49 | 0,66 |
| `laya` (EN) | C) decisão (421M) | 40,9% | 67,9% | 7,1% | 48,9% | 1 100 ms | 4,3 | 0,15 | 0,64 |
| `qwen3.5-0.8b-logprob` | D) genérico, prompt/readout do Jeff | 47,8% | 83,0% | 4,0% | 66,3% | 2 040 ms | 7,8 | 0,13 | 0,71 |
| `qwen3.5-0.8b-chat` | A) generativo | 37,1% | 100% | 0,0% | 57,6% | 2 598 ms | 9,9 | 0,37 | 0,75 |
| `qwen3.5-2b-chat` | A) generativo | 77,4% | 58,5% | 0,0% | 96,0% | 3 582 ms | 13,9 | 0,06 | 0,79 |
| `qwen3.5-4b-chat` | A) generativo | **88,1%** | 28,3% | 1,0% | **98,0%** | 8 644 ms | 33,3 | 0,06 | 0,81 |
| `nli-mdeberta` | zero-shot | 27,7% | 92,5% | 7,1% | 39,1% | 1 102 ms | 4,3 | 0,09 | 0,68 |
| `gliclass-edge` | zero-shot | 44,0% | 96,2% | 1,0% | 64,3% | 98 ms | 0,4 | 0,23 | 0,74 |
| `e5-zeroshot` | zero-shot | 28,9% | 75,5% | 69,7% | 96,7% | 24 ms | 0,1 | – | 0,64 |

### O que os números dizem

1. **O problema tem duas partes de dificuldade muito diferente.** *Qual intenção* (luz? timer? pergunta?) é
   fácil para quase todo modelo bom: Jeff, decider e os Qwen 2B/4B acertam 91–98% quando ativam. *Se a fala é
   dirigida ao assistente* é o difícil — e é exatamente o que define um porteiro.
2. **Modelos de decisão zero-shot classificam o tema, não o destinatário.** O Jeff ativa com 0,94 de confiança
   em "Ontem a luz da sala queimou de novo" e com 0,97 em "Pergunta pra Alexa se vai chover amanhã" (dita a
   outra pessoa). Os erros de falsa ativação se concentram em narrativas sobre dispositivos, TV ao fundo e
   pedidos a outras pessoas. Separar a pergunta (`noul` "é dirigido à Alexa?") só move o ponto na mesma curva:
   falsas ativações 45% → 17%, perdidos 4% → 21%.
3. **Dados do domínio vencem especialização genérica nessa parte.** Um classificador e5 + regressão logística
   treinado com só 64 frases tem a menor falsa ativação (11%) a 27 ms, mas erra mais a intenção (86,6%) e
   **não aceita classes novas sem re-treino**.
4. **Encoders de decisão pequenos (Julia-1, Laya) e zero-shot clássicos (NLI, GLiClass, e5) não servem como
   porteiro neste caso sem fine-tuning**: ativam em 68–100% das falas irrelevantes. Julia-1 nunca escolhe `ignore`.
5. **Especialização em decisão é o efeito mais limpo do experimento.** Mesmo modelo-base, mesmo prompt, mesmo
   readout, mesmo custo: Qwen3.5-0.8B original 47,8% / 83% de falsa ativação vs. Jeff 79,2% / 45%.
   **+31 pontos só pelo fine-tuning de decisão.** Gerando JSON, o 0,8B original cai para 37%.
6. **A técnica de serving pesa tanto quanto o modelo na CPU.** Jeff e decider têm o mesmo tamanho e qualidade
   parecida (79% vs 79%), mas o decider com **cache de schema** (opções primeiro; o prefixo de ~186 tokens é
   computado uma vez e só os ~17 tokens da fala são processados) roda em 542 ms contra 3 051 ms.
7. **Calibração**: decider ECE 0,02 (excelente), Jeff 0,10–0,16, Qwen 2B/4B 0,06 (usando a probabilidade do
   1º token do rótulo). Encoders zero-shot e o e5-logreg são mal calibrados (0,23–0,49), mas o e5-logreg tem o
   melhor **AUROC (0,89)**: a confiança dele *ordena* bem acertos e erros mesmo sem ser probabilidade "honesta" —
   e para cascatas é a ordenação que importa.
8. **Idioma**: Jeff e decider se declaram "English only", mas funcionam em português. O Jeff foi *melhor* com
   descrições das opções em português (82,4% vs 79,2%); o decider foi melhor com descrições em inglês.

## Cascatas: o melhor dos dois mundos

Simulado sobre as predições salvas ([bench/cascade.py](../bench/cascade.py)) e implementado como backend
(`type: cascade`). O estágio 1 decide sozinho quando a confiança ≥ τ; abaixo disso escala.

| cascata | τ | escalado | acurácia | falsa ativação | perdidos | latência média |
|---|---|---|---|---|---|---|
| só e5-logreg | – | 0% | 86,8% | 11,3% | 2,0% | 29 ms |
| e5-logreg → decider (cache) | 0,30 | 16% | 89,3% | 7,5% | 4,0% | **119 ms** |
| e5-logreg → Jeff | 0,30 | 16% | 91,2% | 5,7% | 4,0% | 524 ms |
| e5-logreg → Qwen 4B | 0,30 | 16% | **93,7%** | **3,8%** | 3,0% | 1 457 ms |
| e5-logreg → Qwen 4B | 0,35 | 35% | 96,9% | 5,7% | 2,0% | 3 045 ms |

Ressalva: τ foi varrido no próprio conjunto de teste; o ponto ótimo (0,35) é otimista. Os números com
τ = 0,30 (valor redondo, escolhido antes de olhar o resultado do Jeff/4B) são os mais honestos.

## Fase 2 — porteiro na frente do LLM (ponta a ponta, pela API real)

80 falas (amostra uniforme das 6 classes), cada uma enviada a `POST /v1/route` com `wait_llm=true`:
decisão → rota → executor simulado ou LLM local (Qwen3.5-2B para `LLM`, 4B para `LLM_LARGE`, até 96 tokens).
Baseline: sem porteiro, toda fala vai ao LLM 2B. ([bench/pipeline.py](../bench/pipeline.py))

| estratégia | tempo total | tempo decidindo | chamadas LLM | desperdiçadas | perdidas | falsa ativação | acerto | "acende a luz" ponta a ponta |
|---|---|---|---|---|---|---|---|---|
| sem porteiro (tudo → LLM 2B) | 178 s | – | 80 | **62** | – | 100% | – | – (vira conversa) |
| **cascata e5 → decider** | 143 s | **8,9 s** | **20** | 2 | 0 | **3,7%** | **93,8%** | **66 ms** |
| decider sozinho | 138 s | 43 s | 24 | 5 | 0 | 25,9% | 85,0% | 535 ms |
| Qwen 4B como router | 795 s | 681 s | 23 | 5 | 1 | 25,9% | 87,5% | 8 600 ms |

- O porteiro evitou **75% das chamadas ao LLM** (60 de 80) e 60 das 62 respostas indevidas.
- O **tempo total** caiu só ~20% vs. sem porteiro: respostas a conversa de fundo são curtas (~19 tokens) e as
  perguntas reais são longas (e as `complex` vão ao 4B). O ganho maior não é de CPU, é de **comportamento**
  (não responder ao que não é com ele) e de **latência dos comandos**.
- Usar o próprio LLM como router é o pior dos mundos: **5,6× mais tempo total**, e cada comando simples
  espera a decisão de 8,6 s.

## Escalonamento de intenções e classes dinâmicas

60 falas (amostra uniforme), classes passadas **na requisição**: `gate` = 2 opções (ignorar vs. pedido);
`n6` = taxonomia base; `n12/n20/n32` = base + intenções domésticas distratoras que não correspondem a nenhuma
fala do teste (escolher uma é erro). Tabela completa em [REPORT.md](../runs/bench/REPORT.md#escalonamento-de-intenções-classes-definidas-na-requisição-60-falas).

| backend | 2 opções (gate) | 6 | 12 | 20 | 32 | latência 6 → 32 opções |
|---|---|---|---|---|---|---|
| `decider-0.8b-schema` | 76,7% (FA 63%) | 80,0% | 81,7% | 81,7% | 76,7% | 527 → 542 ms (**constante**: opções ficam no prefixo cacheado) |
| `jeff-0.8b` | 60,0% (FA 11%, perdidos 58%) | 76,7% | 71,7% | 70,0% | 63,3% | 2 861 → 5 654 ms (linear no nº de tokens das opções) |
| `nli-mdeberta` | 68,3% | 35,0% | 35,0% | 35,0% | 35,0% | 1 008 → 5 110 ms (1 forward por opção) |
| `julia-1` | 68,3% | 38,3% | 30,0% | 31,7% | 1,7% | 168 → 215 ms (acima de 20 opções escolhe distrator 93%) |
| `gliclass-edge` | 73,3% | 51,7% | 33,3% | 30,0% | 15,0% | 91 → 180 ms |
| `e5-zeroshot` | 73,3% | 33,3% | 11,7% | 11,7% | 11,7% | ~22 ms |
| treinados (tfidf, e5-logreg, e5-knn) | – | – | – | – | – | não decidem classes que não viram |

- **Decoders de decisão (Jeff, decider) degradam devagar** com mais classes: −4 a −13 pontos de 6 para 32
  opções; a falsa ativação do Jeff cresce (37% → 68%): mais intenções plausíveis "puxam" falas irrelevantes.
- **Encoders e zero-shot clássicos colapsam** com distratores (escolhem a intenção errada mas parecida).
- **Custo**: com cache de schema, opções extras são grátis por requisição; sem cache (Jeff), cada opção custa
  tokens a cada decisão; no NLI, cada opção custa um forward inteiro.
- **Redefinir a tarefa como binária (gate) não ajudou** nenhum decoder: o Jeff fica conservador demais
  (perde 58% dos pedidos), o decider permissivo demais (63% de falsa ativação). A formulação com intenções
  explícitas + `ignore` descritivo funcionou melhor.

## Respostas às perguntas do experimento

**Um modelo especializado em decisão é significativamente mais rápido que um LLM generativo?**
Contra um LLM de qualidade equivalente, sim: o decider (79%, 542 ms, 2,2 CPU-s) vs. o Qwen 4B (88%, 8,6 s,
33 CPU-s) é 16× mais rápido e 15× mais barato, com 9 pontos a menos de acurácia. Contra um LLM *do mesmo
tamanho*, a vantagem de "não gerar texto" é pequena para rótulos curtos (0,8B: 2,0 s com 1 forward vs. 2,6 s
gerando JSON) — o ganho real vem de (a) a especialização tornar útil um modelo pequeno e (b) o layout cacheável.

**Um modelo pequeno consegue decidir se uma fala é destinada ao assistente?**
Sozinho e zero-shot, não com confiabilidade de produto: os melhores modelos de decisão erram 38–45% das falas
irrelevantes (por limiar dá para trocar por pedidos perdidos, não eliminar). Com dados do domínio, sim: um
classificador de 118M com 64 exemplos chega a 11%, e a cascata classificador → modelo de decisão/LLM fica em
4–8% de falsa ativação e 2–4% de perdidos. A dificuldade está no *destinatário*, não na intenção.

**Qual é a latência ponta a ponta?** Nesta VM de 4 vCPUs: comando doméstico decidido e executado em **66 ms**
com a cascata (estágio 1 resolve 84% das falas); 535 ms com o decider sozinho; 8,6 s com o LLM 4B como router.
Respostas de conhecimento: +3 s (2B) a +10 s (4B) de geração. O STT não foi medido (fase 4).

**Qual é o custo computacional?** CPU-segundos por decisão: TF-IDF 0,004; e5 0,11; decider com cache 2,2;
Jeff 7,3; Qwen 2B 13,9; Qwen 4B 33,3. Memória: e5 ~0,6 GB; decider/Jeff em fp32 3,5–4 GB; 4B Q4 4,4 GB.

**Ele consegue funcionar continuamente em uma máquina doméstica?** Supondo uma fala a cada ~3 s em escuta
contínua: a cascata ocupa ~5% de 4 núcleos; o decider com cache ~18%; o Jeff (PyTorch fp32, sem cache)
~60%; o LLM 4B não acompanha o fluxo (8,6 s por fala > 3 s entre falas). Num PC com GPU tudo cabe com folga.

**A especialização melhora significativamente a confiabilidade?** Sim, e é o resultado mais limpo: mesma base,
mesmo prompt, mesmo custo, +31 pontos de acurácia e falsa ativação 83% → 45% (Qwen3.5-0.8B → Jeff). E
calibração: ECE 0,02–0,10 nos modelos de decisão. A especialização *no domínio* (exemplos do assistente) é o
que resolve a parte do destinatário.

**Melhor um modelo especializado ou um modelo pequeno de uso geral?** No tamanho 0,8B, o especializado
ganha com folga (79% vs 37–48%). Um generalista precisa de 2B para empatar (77%, com 2× o custo do Jeff e 6×
o do decider) e de 4B para superar (88%, 4–15× o custo).

**O modelo consegue funcionar como router antes de um LLM maior?** Sim. No fluxo real, o porteiro evitou 75%
das chamadas ao LLM e 60 de 62 respostas indevidas, sem perder nenhuma pergunta que precisava do LLM
(cascata: 20 chamadas, 18 necessárias, 0 perdidas).

**Quanto processamento e quantas chamadas ao modelo maior podem ser evitados?** Neste fluxo (37% de falas
irrelevantes), 75% das chamadas. Em escuta contínua real a proporção de falas irrelevantes é muito maior, e a
economia cresce junto. Em tempo de CPU, a economia depende de quão caras seriam as respostas indevidas: aqui
foram curtas (~20% do tempo total); se o LLM fosse chamado para *decidir* (LLM como router), o porteiro evita
**82% do tempo total** (795 s → 143 s).

**A abordagem continua funcionando quando a quantidade de intenções aumenta?** Para decoders de decisão,
sim, com perda gradual (−4 a −13 pontos de 6 → 32 opções) e, com cache de schema, sem custo extra de latência.
Encoders pequenos e zero-shot clássicos não.

**Como o desempenho muda quando as classes são definidas dinamicamente?** Os modelos de decisão aceitam
classes novas na requisição sem re-treino (é o ponto forte deles); classificadores treinados não. A redação das
opções pesa: descrever bem o `ignore` importou mais que transformar a tarefa em binária.

**A saída probabilística/calibrada é útil para definir thresholds?** Sim, de duas formas diferentes:
(1) *calibração* (decider ECE 0,02) permite escolher τ pelo significado ("só agir com ≥ 90%") sem dados
rotulados; (2) *ordenação* (AUROC; o e5-logreg é mal calibrado mas tem AUROC 0,89) é o que faz cascatas
funcionarem. Limiar sozinho não resolve o porteiro: no Jeff, τ = 0,7 baixa a falsa ativação de 45% para 13%
mas perde 26% dos pedidos. Usar a baixa confiança para *escalar* (cascata) em vez de *ignorar* foi o que deu
o melhor resultado.

## Onde a abordagem funciona e onde não funciona

**Funciona**: decidir a intenção entre opções descritas em linguagem natural, inclusive classes novas definidas
na hora; probabilidades calibradas; um passo só, sem parsing; escala de opções com custo constante (com cache).
Com GPU, cabe em dezenas de milissegundos.

**Não funciona (ainda) sozinho**: julgar *a quem* uma fala se dirige (o modelo lê "sobre o quê"); modelos
encoder pequenos zero-shot neste domínio; latência de dezenas de ms em CPU modesta com o serving padrão
(PyTorch fp32 sem cache = segundos).

**Custo/benefício**: a arquitetura recomendada pelo experimento é em camadas — um classificador minúsculo
treinado no domínio (ms) como primeiro filtro, um modelo de decisão com schema cacheado para os casos
incertos e para intenções/classes dinâmicas, e o LLM só para o que precisa de geração.

## Máquina local (re-medição em 04/10/2026)

PC doméstico **em uso normal** (não dedicado): Windows 11 + WSL2, i5-9400F (6 núcleos, AVX2, sem AVX-512),
16 GB, **sem GPU utilizável** (Radeon RX 580). Detalhes, escolha de threads e problemas em
[02-ambiente.md](02-ambiente.md#máquina-local-retomada-em-04102026). Resultados em `runs/bench-local/`
([REPORT.md](../runs/bench-local/REPORT.md)); os da nuvem continuam em `runs/bench/`.
Comando: `BENCH_DIR=runs/bench-local THREADS=4 TORCH_THREADS=3 scripts/bench_all.sh`.

### Resultado principal — local vs. nuvem

| backend | acurácia | falsa ativação | perdidos | p50 local | p50 nuvem | CPU-s local | CPU-s nuvem |
|---|---|---|---|---|---|---|---|
| `e5-logreg` | 86,8% | 11,3% | 2,0% | **17 ms** | 27 ms | 0,05 | 0,11 |
| `decider-0.8b-schema` | 78,6% | 37,7% | 6,1% | **350 ms** | 542 ms | 1,14 | 2,15 |
| `jeff-0.8b` | 79,2% | 45,3% | 4,0% | 2 802 ms | 3 051 ms | 7,7 | 7,3 |
| `jeff-0.8b-pt` | 82,4% | 37,7% | 2,0% | 2 864 ms | 3 072 ms | 8,2 | 7,5 |
| `qwen3.5-0.8b-logprob` | 46,5% (nuvem 47,8%) | 83,0% | 4,0% | 1 910 ms | 2 040 ms | 7,7 | 7,8 |
| `qwen3.5-4b-chat` | 88,7% (nuvem 88,1%) | 28,3% | 0,0% (nuvem 1,0%) | 10 340 ms | 8 644 ms | 43,5 | 33,3 |

- **A qualidade reproduziu exatamente** nos modelos PyTorch (mesmas predições: acurácia, falsa ativação, ECE e
  estabilidade idênticos). Nos modelos do llama.cpp houve diferenças de 1–2 falas (commit mais novo do
  llama.cpp e outro conjunto de instruções da CPU) — ruído, não mudança de conclusão.
- Estabilidade do `qwen3.5-4b-chat` à fala sem acentos/pontuação: **93,7%** (não tinha sido medida na nuvem).

Cascatas (simuladas sobre as predições locais, τ = 0,30):

| cascata | acurácia | falsa ativação | perdidos | latência média local | nuvem |
|---|---|---|---|---|---|
| e5-logreg → decider (cache) | 89,3% | 7,5% | 4,0% | **79 ms** | 119 ms |
| e5-logreg → Jeff | 91,2% | 5,7% | 4,0% | 478 ms | 524 ms |
| e5-logreg → Jeff (opções PT) | 91,8% | 7,5% | 2,0% | 493 ms | – |
| e5-logreg → Qwen 4B | 94,3% | 3,8% | 2,0% | 1 739 ms | 1 457 ms |

Pipeline ponta a ponta (80 falas, `/v1/route`, com aquecimento):

| estratégia | tempo total | decidindo | chamadas LLM | desperdiçadas | falsa ativação | acerto | comando doméstico ponta a ponta |
|---|---|---|---|---|---|---|---|
| sem porteiro (tudo → LLM 2B) | 193 s | – | 80 | 62 | 100% | – | – |
| **cascata e5 → decider** | **119 s** | **5,8 s** (73 ms/fala) | 20 | 2 | 3,7% | 93,8% | **50 ms** |
| decider sozinho | 130 s | 31,8 s | 24 | 5 | 25,9% | 85,0% | 388 ms |
| Qwen 4B como router* | 1 011 s | 881 s | 23 | 5 | 25,9% | 87,5% | 11 000 ms |

\* medido antes de o aquecimento entrar no script; a 10 s por decisão o efeito do aquecimento é desprezível.

Escalonamento (60 falas): acurácias idênticas às da nuvem em todos os cenários. Latência do decider com cache
**constante** de 2 a 32 opções (456–522 ms nesta rodada, com o host mais carregado que na bateria principal);
Jeff 1 902 → 5 364 ms (linear nas opções).

### O que mudou nas conclusões

**Não mudou** (confirmado numa segunda máquina, com outra CPU e outra versão do llama.cpp):
intenção fácil / destinatário difícil (38–45% de falsa ativação zero-shot); especialização vale ~+33 pontos
(46,5% → 79,2%, mesmo prompt, mesmo custo); a cascata e5 → decider é o melhor custo/benefício; o porteiro
evita 75% das chamadas ao LLM sem perder perguntas; usar o LLM como router é o pior caso (8,5× o tempo da cascata).

**Mudou ou ficou mais preciso:**

1. **"Um desktop é 3–6× mais rápido que a VM" é falso para um PC de 6 núcleos de 2018.** Ele empata com a VM
   de 4 vCPUs: 1,5× mais rápido nos modelos PyTorch pequenos (decider, e5), igual no Jeff, **0,8×** no Qwen 4B
   (sem AVX-512, e disputando CPU com o uso normal da máquina). As latências da nuvem eram uma boa estimativa de
   um PC doméstico modesto, não um piso pessimista.
2. **O cache de schema pesa ainda mais aqui: decider 8× mais rápido que o Jeff** (350 vs 2 802 ms; na nuvem 5,6×).
3. **Novo: configuração de threads importa tanto quanto a escolha do modelo.** Numa máquina compartilhada, usar
   todos os núcleos deixou o decider 4,7× mais lento (1 699 vs 359 ms), o e5 5× e a geração do llama.cpp 7,5×.
   Metade dos núcleos foi o ótimo. Um assistente que roda em segundo plano num PC em uso precisa disso por padrão.
4. **Novo: partida a frio.** As duas primeiras decisões de um schema no decider custam 10–25 s aqui (o cache só
   é montado na 2ª vez). Para um assistente, o schema tem de ser pré-carregado na subida do serviço.
5. **Operação contínua**: a cascata custa 73 ms e ~0,23 CPU-s por fala em média (≈ 8% de um núcleo a uma fala a cada 3 s) —
   cabe com folga mesmo neste PC. O Jeff em PyTorch (2,8 s e ~2,8 núcleos por fala) e o 4B (10 s) não cabem.
6. **Continua sem verificação**: os ~22–30 ms do Jeff em GPU. Esta máquina não tem GPU utilizável pelo PyTorch;
   o experimento de LoRA (item 1 abaixo) segue bloqueado por hardware.

Ressalva de método: as latências locais foram medidas com a máquina em uso (carga do host variável; a mesma
configuração do decider mediu 350 ms numa rodada e ~500 ms em outra). As acurácias não dependem disso.

## Experimento 2 — decider em GGUF no llama.cpp com o prefixo do schema restaurado (04/10/2026, máquina local)

Feito no lugar do LoRA, que precisa de GPU. Pergunta: dá para juntar os kernels de CPU do llama.cpp com o cache
de schema do decider? Hipótese registrada antes: cair de ~540 ms para ~100–200 ms.

**Como** ([lab/backends/decider_llama.py](../lab/backends/decider_llama.py), tipo `decider_llama`):

1. O decider-0.8b foi convertido para GGUF Q8_0 (`scripts/convert_decider_gguf.sh`; o projeto só publica GGUF do
   2B e do 4B). Não há cabeça extra: o decider lê os logits das letras no LM head.
2. O backend monta o prompt *schema-first* em ids de tokens, igual ao `decider.prompt` (pergunta + opções =
   prefixo; `Context:` + fala + `Answer: (` = sufixo), e pede ao `llama-server` (`/completion`, 1 token) os logits
   das letras; softmax com a temperatura do `decider_config.json` (1,03).
3. Três modos de reaproveitar o prefixo: `none` (recalcula tudo), `slot` (`cache_prompt` do servidor) e `restore`
   (calcula o prefixo uma vez, `POST /slots/0?action=save`; antes de cada decisão, `action=restore`).

**Resultado** (159 falas, `--perturb`, `THREADS=4`; mesma máquina e mesma rodada de carga do host):

| serving do decider-0.8b | acurácia | falsa ativação | p50 | p95 | CPU-s | RAM do servidor | tokens processados por fala |
|---|---|---|---|---|---|---|---|
| PyTorch fp32 + cache de schema (`decider.serve`) | 78,6% | 37,7% | 350 ms | 438 ms | 1,14 | 3,5 GB | ~17 |
| llama.cpp Q8_0, sem cache | 78,6% | 37,7% | 1 427 ms | 1 623 ms | 5,90 | 1,0 GB | ~204 |
| llama.cpp Q8_0, `cache_prompt` do slot | = | = | ~1 350 ms | – | 5,7 | 1,0 GB | ~203 (**não reaproveita**) |
| **llama.cpp Q8_0, prefixo restaurado** | 78,6% | 37,7% | **204 ms** | 314 ms | **0,79** | **1,0 GB** | ~17,5 (+5 ms do restore) |
| (referência) Jeff, PyTorch fp32, sem cache | 79,2% | 45,3% | 2 802 ms | 3 126 ms | 7,74 | 3,9 GB | prompt inteiro |

- **Paridade**: 159 de 159 decisões idênticas às do PyTorch; diferença média de probabilidade 0,011 (máx. 0,07),
  efeito da quantização Q8. ECE 0,07 (PyTorch: 0,02) — a calibração piora um pouco, a ordenação não (AUROC 0,81).
- **Classes dinâmicas**: latência constante de 2 a 32 opções (198–237 ms), mesmas acurácias do PyTorch em todos os
  cenários (inclui a renderização "larga" de mais de 10 opções). Cada schema novo custa um prefill (~1,5 s) e um
  arquivo de estado de 21–26 MB.
- **Cascata** e5-logreg → decider GGUF (τ = 0,30): 89,3% / 7,5% de falsa ativação / **56 ms** de média (simulada).
  No pipeline real pela API (`cascade-e5-decider-gguf`): 128 s no total, 5,9 s decidindo (73 ms por fala), 3,7% de
  falsa ativação, 93,8% de acerto, 0 perguntas perdidas — igual à cascata com PyTorch, com 2,5 GB a menos de RAM.

**Conclusões**

1. **Hipótese confirmada no limite superior**: 350 → 204 ms (1,7×) e 31% menos CPU, com 3,5× menos memória.
   Contra o mesmo GGUF sem cache, o prefixo restaurado vale **7×**; contra o Jeff em PyTorch, **14×**.
2. **Os dois ganhos são independentes e se multiplicam**: kernels do llama.cpp ≈ 2× (2 802 ms do Jeff em PyTorch →
   1 427 ms do decider em GGUF, ambos processando o prompt inteiro) e cache de schema ≈ 7×.
3. **O `cache_prompt` do llama-server não serve para isso no Qwen3.5.** O estado recorrente das camadas Gated
   DeltaNet não pode ser "rebobinado" até o fim do prefixo depois que a fala anterior passou por ele, e o servidor
   reprocessa tudo (com ou sem `--cache-ram`). Só o save/restore explícito de um estado que termina exatamente no
   fim do prefixo funciona.
4. O que sobra dos 204 ms é taxa de tokens: ~17 tokens de sufixo a ~90–110 tok/s. Próximos ganhos possíveis:
   Q4_K_M (na VM o prefill foi 1,35× mais rápido que em Q8_0, a verificar a paridade) e sufixo mais curto.
5. **Não muda o problema principal**: é o mesmo modelo, com os mesmos 37,7% de falsa ativação. O experimento
   barateia o 2º estágio da cascata; o destinatário continua dependendo de dados do domínio (item 1 abaixo).

Decisão: o backend padrão **continua** `cascade-e5-decider` (funciona só com o `setup.sh`). O
`cascade-e5-decider-gguf` é a opção recomendada quando a RAM é o gargalo (é o caso deste PC de 16 GB); exige
`scripts/convert_decider_gguf.sh` e `scripts/services.sh start decider-gguf`.

Limitações: um slot só (uma decisão por vez; o restore troca o estado do slot), testado só com o 0.8B em Q8_0 e
só nesta máquina; o Jeff não foi convertido (o layout dele é *state-first* e o readout é uma camada separada do
LM head, então não há prefixo cacheável nem conversão direta).

## Próximos experimentos sugeridos

0. **Estado em 04/10/2026**: o item 2 foi feito (seção acima). O item 1 continua sendo o mais importante e está
   **bloqueado por hardware**: a máquina local não tem GPU utilizável pelo PyTorch (Radeon RX 580). Alternativas
   sem GPU, ainda não tentadas: treinar o LoRA numa GPU alugada/Colab e só servir aqui; ou fine-tuning do
   classificador e5 com os mesmos 1–2 mil exemplos (treina em CPU em minutos), que ataca o mesmo problema pelo
   1º estágio da cascata.
1. **Fine-tuning de domínio de um modelo de decisão** (LoRA do Jeff com o adapter kit, ou o decider) com
   ~1–2 mil frases do assistente (geradas + revisadas), atacando especificamente o "destinatário". É a hipótese
   mais forte para tirar o porteiro de 38% para < 10% de falsa ativação sem o classificador separado.
2. **Jeff/decider em GGUF no llama.cpp** com estado de prefixo salvo (`/slots save/restore`) para juntar os
   kernels CPU do llama.cpp com o cache de schema — deve cair de ~540 ms para ~100–200 ms nesta VM.
3. **Contexto conversacional no estado** (as últimas falas + se a Alexa acabou de falar) — o destinatário
   muitas vezes só é decidível com contexto.
4. **Fase 3 (celular ↔ PC)**: a API já aceita `HOST=0.0.0.0 scripts/lab.sh`; a UI funciona no navegador do celular.
5. **Fase 4 (voz contínua)**: whisper.cpp (ou Moonshine) local com VAD → `/v1/route`; medir latência total
   fala → ação e o efeito de erros reais de ASR. A UI já tem uma prévia com a Web Speech API do navegador.
6. **Dataset maior e independente** (gravações reais, várias pessoas) para validar os limiares fora do conjunto
   em que foram escolhidos.
