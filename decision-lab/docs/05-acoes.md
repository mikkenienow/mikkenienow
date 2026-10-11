# Do roteador a ações reais — adaptador de ferramentas (11/10/2026)

Parte do estado aprovado (roteador e5 → decider, commit `fd8bdd1`). O roteador não foi trocado nem re-treinado e o
dataset de teste (`data/test.jsonl`) não foi tocado. Tudo novo está em arquivos novos.

## O ciclo

```
entrada ──► roteador (e5 → decider) ──► validação da decisão ──► escolha da ferramenta ──► validação dos parâmetros
        "é comigo? qual intenção?"      fora da taxonomia → nada   só da lista permitida      tipos fechados, faixas
                                        "ignorar" → nada
        ──► confirmação (se sensível) ──► ferramenta ──► resultado ──► log (runs/decisions.jsonl)
```

`POST /v1/act {"input": "...", "client": "<quem pediu>"}` faz o ciclo inteiro e devolve a decisão e `tool`
(`name`, `args`, `status`, `say`, `result`). `POST /v1/act/confirm {"token", "approve"}` responde a um pedido de
confirmação. `GET /v1/tools` lista o que é permitido. `/v1/route` e os benchmarks antigos ficaram como estavam.

| Arquivo | Papel |
|---|---|
| `lab/tools/__init__.py` | `Tool`, `Param`, `ToolRegistry`: lista fechada e validação de parâmetros |
| `lab/tools/builtin.py` | as 15 ferramentas, a extração de parâmetros (regras) e as frases de resposta |
| `lab/actions.py` | `Planner` (escolhe a ferramenta) e `ActionEngine` (travas, confirmação, execução) |
| `tests/test_tools.py` | 11 testes das travas (sem modelo, sem rede) |
| `bench/tools_eval.py`, `data/tools_eval.jsonl` | avaliação em 75 falas novas |
| `bench/phase3_check.py` | verificação ponta a ponta pela API, do ponto de vista de um cliente |

## O que o modelo pode e não pode fazer

- O modelo **nunca executa nada** e nenhum texto do usuário vira comando. Ele só (a) classifica a fala e (b) aponta
  uma ferramenta **de uma lista fechada**. Se apontar algo fora da lista, a ação é rejeitada.
- **Não existe ferramenta de shell, arquivo arbitrário ou rede.** Uma ferramenta só enxerga o `ToolContext`: a casa
  simulada, o arquivo de anotações e o canal de eventos da UI.
- Os parâmetros saem do texto por **regras determinísticas** (regex), não do modelo, e passam por um esquema:
  tipos, valores permitidos, faixas e tamanho máximo. Parâmetro desconhecido é erro. Faltou algo → `needs_info` e
  nada roda.
- **Ações sensíveis pedem confirmação**: ficam pendentes com um token de uso único que expira em 60 s; só o mesmo
  cliente que pediu pode confirmar (por botão ou falando "sim" / "não, deixa").

### As 15 ferramentas

| Ferramenta | Efeito | Sensível |
|---|---|---|
| `info.time`, `info.date`, `info.system_status` | **real**: relógio do PC, uso de CPU/memória/disco | não |
| `timer.create`, `timer.list` | **real**: um timer de verdade no servidor; ao terminar, um evento chega à interface (aviso + vibração) | não |
| `timer.cancel_all` | **real** | **sim** |
| `note.add`, `note.list` | **real**: grava/lê `runs/notes.jsonl` | não |
| `note.clear` | **real**: apaga o arquivo | **sim** |
| `home.set_device` | simulado: liga/desliga, abre/fecha um dispositivo da casa simulada | **sim quando abre porta ou portão** |
| `media.play`, `media.pause`, `media.set_volume` | simulado | não |
| `llm.answer`, `llm.answer_large` | encaminha ao LLM local (resposta assíncrona) | não |

## Como a ferramenta é escolhida

O roteador devolve uma intenção (6 classes). Dentro dela ainda é preciso escolher: "que horas são?" e "qual a capital
do Canadá?" são ambas *pergunta*, mas só uma se responde localmente. Três seletores foram medidos:

- **regras**: uma regex por ferramenta;
- **modelo**: o próprio modelo de decisão (decider GGUF) escolhe entre as *descrições* das ferramentas — é o uso de
  classes dinâmicas, o ponto forte dele;
- **híbrido** (adotado): vale a regra **se ela casar dentro da rota que o roteador escolheu** (dois sinais
  independentes concordando); senão, o modelo escolhe.

E dois escopos para o modelo: só as ferramentas **da rota** do roteador, ou **todas** as permitidas.

## Avaliação

`data/tools_eval.jsonl`: 75 falas novas em PT-BR escritas para este teste (67 dirigidas ao assistente, 8 não), com
ferramenta, parâmetros e desfecho esperados; inclui paráfrases, erros de transcrição, pedidos incompletos, ações
sensíveis e 3 "pegadinhas" (perguntas gerais com palavras de ferramenta: "quantas **horas** tem uma semana?").
O script confere que nenhuma fala repete o dataset congelado — pegou 7 repetições na primeira versão, que foram trocadas.

**Desfecho correto** = ferramenta certa + parâmetros certos + status certo (executou / pediu confirmação / pediu o
que faltava / ignorou).

| seletor | escopo | rota-ouro (isola o adaptador) | **ponta a ponta** (roteador real) | chamadas ao modelo (ponta a ponta) |
|---|---|---|---|---|
| regras | rota | 85,3% | 74,7% | 0 |
| modelo | rota | **93,3%** | 81,3% | 48 de 75 |
| híbrido | rota | 92,0% | 80,0% | 20 de 75 |
| regras | todas | 84,0% | 78,7% | 0 |
| modelo | todas | 92,0% | **88,0%** | 66 de 75 |
| **híbrido (adotado)** | **todas** | 92,0% | **88,0%** | **27 de 75** |

O roteador acertou a intenção em 88,0% destas falas. Cada chamada ao modelo custa ~220–240 ms (mediana); a decisão
do roteador, ~20 ms; a ferramenta, < 1 ms.

### O que os números dizem

1. **O modelo de decisão escolhe ferramenta melhor que regras** (93% contra 85% com a intenção dada): entende
   paráfrases que ninguém previu ("o servidor tá aguentando?" → estado do PC).
2. **Deixar o segundo passo escolher entre todas as ferramentas corrige erros de intenção do roteador**: +6,7 pontos
   ponta a ponta (81,3% → 88,0%). Exemplo real: "me lembra de comprar pão" é classificado como *pergunta* pelo
   roteador e ainda assim vira `note.add`. O roteador fica com o que faz bem ("é comigo?") e a ferramenta é decidida
   por quem aceita classes novas sem re-treino.
3. **Regras aplicadas entre rotas são perigosas**: "pode parar o alarme" casava com *pausar a mídia* e executava,
   em vez de pedir confirmação para cancelar o timer. Por isso, no híbrido, regra só vale dentro da rota do roteador.
4. **O híbrido dá a mesma acurácia do modelo com 41% das chamadas** (27 contra 66).

### Segurança, medida

| | resultado |
|---|---|
| ferramenta sensível executada sem confirmação | **0** em todas as configurações (é estrutural: o motor não tem caminho para isso; coberto pelos testes) |
| "Pai, abre a porta pra mim!" (pedido a outra pessoa, ação sensível) | ignorado em todas as configurações |
| ação em fala **não** dirigida ao assistente (ponta a ponta) | **1 de 8**: "A Alexa da vizinha toca música o dia inteiro" → tocou música (simulada). É o problema conhecido do destinatário, herdado do roteador |
| pedido dirigido que foi ignorado | 2 de 67 ("anota aí: comprar ração do cachorro", "limpa as anotações") |
| resposta local errada a pergunta geral (as 3 pegadinhas) | **3 de 3 erradas**: "que dia foi a proclamação da república?" recebeu a data de hoje |

Demais erros do padrão adotado: "tá muito alto isso aí" (ferramenta certa, não extraiu "abaixar"), "chega de música"
(tocou em vez de pausar), "falta quanto pro timer acabar?" (regra de criar timer casou primeiro).

### Limitações

- **75 falas escritas por mim**, o mesmo viés do dataset original. Servem para comparar seletores, não para estimar
  acurácia em casa.
- **Um ajuste foi feito depois de ver um erro**: as palavras de anotação ("me lembra", "anota") passaram a contar
  como regra de `note.add`. Antes disso o híbrido/todas dava 86,7% ponta a ponta; os 88,0% são levemente otimistas.
  Um bug de acentuação na extração ("anota **aí**") também foi corrigido depois da primeira execução (regras:
  82,7% → 85,3%). Nenhuma regra foi escrita para as paráfrases que o conjunto mostrou.
- **Extração de parâmetros é por regex**: funciona para o previsto (durações por extenso, cômodos, volume) e falha em
  silêncio fora disso — com a diferença de que falhar aqui significa `needs_info`, não ação errada.
- **Pegadinhas**: o modelo de decisão é atraído por palavras ("horas", "dia", "memória RAM"). Para consultas locais
  isso gera resposta errada com cara de certa. Mitigação a testar: descrições mais restritivas ou um limiar de
  confiança próprio para as ferramentas `info.*`.
- **Partida a frio**: o primeiro uso de um schema novo de ferramentas custa segundos (o prefixo é calculado e salvo).
  O servidor agora aquece esse schema ao subir e reaproveita o arquivo salvo entre reinícios (p95 1,8 s → 0,5 s).
- **Um cliente por vez na confirmação**: uma pendência por cliente; pedir outra ação sensível substitui a anterior.
- A casa e a mídia continuam **simuladas**. Nenhum dispositivo físico foi ligado.

## Verificação ponta a ponta pela API

`bench/phase3_check.py` age como um cliente: ping, 12 falas com desfecho esperado repetidas, ação sensível
(pendente → outro cliente é barrado → o dono confirma → token não vale duas vezes), recusa e confirmação faladas,
timer real cujo aviso tem de chegar pelo stream, stream aberto pelo tempo pedido, e envio de 👍. Resultados em
`runs/phase3/` e em [04-fase3.md](04-fase3.md).

## Como rodar

```bash
THREADS=4 TORCH_THREADS=3 SLOT_DIR=$HOME/decision-lab-data/slots scripts/services.sh start decider-gguf llm-large
LAB_BACKEND=cascade-e5-decider-gguf scripts/lab.sh                      # HOST=0.0.0.0 para o celular
.venv/bin/python tests/test_tools.py                                    # travas (11 testes)
.venv/bin/python -m bench.tools_eval --selectors rules,hybrid,model --scope all --router cascade-e5-decider-gguf
.venv/bin/python -m bench.phase3_check                                  # ciclo completo pela API
curl -s localhost:8000/v1/act -H 'content-type: application/json' -d '{"input": "Alexa, timer de 10 segundos"}'
```

`LAB_TOOL_SELECTOR=rules|model|hybrid` e `LAB_TOOL_SCOPE=route|all` trocam o seletor sem editar `config/backends.yaml`.
