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
| `lab/tools/builtin.py` | as 18 ferramentas, a extração de parâmetros (regras) e as frases de resposta |
| `lab/tools/player.py` | biblioteca de músicas e o player do Windows (e o `NullPlayer`, sem som, para testes) |
| `lab/actions.py` | `Planner` (escolhe a ferramenta) e `ActionEngine` (travas, confirmação, execução) |
| `tests/test_tools.py` | 17 testes das travas, da busca de música e do "não sei fazer" (sem modelo, sem rede) |
| `bench/player_check.py` | teste de integração do player: toca de verdade neste PC e confere posição, pausa, volume |
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

### O que é REAL e o que é SIMULADO (18 ferramentas, atualizado em 11/10/2026)

Esta é a lista que vale. "Real" = tem efeito de verdade neste PC; "simulado" = só muda um estado em memória.

| Ferramenta | O que faz de verdade | Situação | Pede confirmação |
|---|---|---|---|
| `info.time`, `info.date`, `info.system_status` | lê o relógio, o calendário e CPU/memória/disco do PC | **real** | não |
| `media.play` | **toca um arquivo de áudio nas caixas do PC**, pelo Windows (MediaPlayer). Com nome: procura nas pastas de música (nome do arquivo e da pasta). Sem nome ("toca uma música"): escolhe uma aleatória | **real** | não |
| `media.pause` / "continua" | pausa e retoma a faixa | **real** | não |
| `media.set_volume` | volume do **player** (0–10); não mexe no volume geral do Windows | **real** | não |
| `media.status` | diz o que está tocando e em que ponto (lido do próprio player) | **real** | não |
| `timer.create`, `timer.list` | timer de verdade no servidor; ao terminar, aviso na tela (e vibração no celular) | **real** | não |
| `timer.cancel_all` | cancela os timers | **real** | **sim** |
| `note.add`, `note.list` | grava/lê `runs/notes.jsonl` | **real** | não |
| `note.clear` | apaga esse arquivo | **real** | **sim** |
| `llm.answer`, `llm.answer_large` | responde com o modelo de linguagem local (Qwen 2B / 4B) | **real** (o texto pode estar errado) | não |
| `system.help` | lista o que é real, o que é simulado e o que não existe | **real** | não |
| `home.set_device` | **só muda um estado em memória** (luz, TV, porta…); nenhum aparelho de verdade é acionado | **SIMULADO** | **sim**, se abrir porta/portão |
| `system.cannot_do` | não faz nada: responde "entendi que era comigo, mas não sei fazer isso" | — | não |

**O que NÃO existe** (e ele diz que não sabe): enviar e-mail ou mensagem, ligar para alguém, comprar ou pedir comida,
marcar compromissos, abrir aplicativos ou sites, tocar música em serviços (Spotify, YouTube) e controlar o Echo Dot
ou aparelhos de verdade.

### Música: como toca, onde procura, o que acontece quando não acha

- **Como**: o servidor (WSL2) mantém um `powershell.exe` com um `System.Windows.Media.MediaPlayer` e conversa com ele
  por JSON (`lab/tools/player.py`). Só toca arquivos que **ele mesmo achou** nas pastas configuradas
  (`config/backends.yaml → tools.music_dirs`; extensões mp3, wav, m4a, wma, aac, flac); o caminho nunca vem do texto.
- **Onde procura**: `C:\Users\Mikke\Music` (10 faixas neste PC) + 3 melodias de domínio público geradas em
  `runs/music` ("Ode à Alegria", "Frère Jacques", "Parabéns pra você"), para sempre haver algo para tocar.
- **Sem nome**: toca uma aleatória **das suas**, e diz que escolheu ("Você não disse qual, escolhi uma").
- **Com nome que não existe**: **não toca nada e pergunta** — "Não achei “Roberto Carlos” nas músicas deste PC (10
  faixas). Algumas que eu tenho: …". A faixa que estiver tocando continua.
- **Como saber se tocou de verdade**: a resposta traz o título e a duração lidos do Windows, e `GET /v1/player` /
  "o que está tocando?" mostram a posição andando. `bench/player_check.py` verifica isso sozinho: abre, a posição
  avança, pausa congela, retoma, volume muda (todas ok). **O que ninguém consegue verificar por software é se há
  alguém ouvindo**: o Windows toca no dispositivo de áudio padrão.
- **Fora do WSL2** (ou `LAB_PLAYER=null`) o player é simulado e as respostas dizem "simulado: nenhum som foi iniciado".

### Quando ele não sabe fazer

Antes, um pedido sem ferramenta virava silêncio ("ignorado") ou uma ação errada. Agora:

| situação | resposta |
|---|---|
| pedido para o assistente sem ferramenta ("manda um e-mail pro chefe", "toca Djavan no Spotify") | **"Entendi que o pedido era para mim, mas ainda não sei fazer isso"** + como ver o que existe |
| ferramenta existe, falta informação ("a luz") | pergunta o que falta; não executa |
| ferramenta existe, não achou o que foi pedido (música inexistente) | diz que não achou e dá opções |
| não era para ele | ignora (e a interface mostra "Ignorei — não era comigo") |

Isso é feito por uma **regra explícita** (verbo de pedido + serviço/coisa que não existe) que vale em qualquer rota e
também quando o roteador diz "ignorar", **desde que a fala comece com "Alexa,"** — assim o silêncio não é confundido
com falta de capacidade. Perguntas ("como faço pra mandar um e-mail?") e lembretes ("me lembra de ligar pro dentista")
**não** disparam a regra.

### Modo direto (cliente de texto)

No uso real pelo celular, 6 de 7 falas sem "Alexa" foram ignoradas, inclusive pedidos claros. A UI agora tem
"Tudo que eu digito é para o assistente" (ligado por padrão): envia `addressed: true`, o roteador não pode mais
responder "não é comigo" e vale a 2ª melhor intenção. Na API o padrão continua `false` (escuta ambiente), então os
benchmarks e o porteiro não mudam. O log guarda `addressed` e `direct_as`.

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

### Rodada de 11/10 (noite): música real, "não sei fazer" e modo direto

Código final em `runs/tools-v2/` (a rodada acima ficou em `runs/tools/`). Seletor híbrido, escopo "todas".

| conjunto | rota-ouro | ponta a ponta (roteador real) |
|---|---|---|
| 75 originais (agora com 18 ferramentas) | 90,7% (era 92,0%) | 86,7% (era 88,0%) |
| **28 novas**: 13 pedidos sem ferramenta, 4 ajuda, 7 música, 4 perguntas-armadilha | **96,4%** (27/28) | **89,3%** (25/28) |

- As 28 novas foram escritas **depois** de ver o comportamento da primeira versão do "não sei fazer", que acertava
  75% (rota-ouro). A regra explícita foi escrita a partir da lista `CANNOT_DO` que eu já tinha declarado e depois
  revisada duas vezes após ver erros ("abre o YouTube", "toca no Spotify"; e dois lembretes que ela quebrou).
  **Os 96,4% são otimistas**; é a medida do que a regra faz com frases parecidas com as que eu vi, não uma estimativa
  de uso real.
- Erros que restam: "põe um som aí" (confundido com volume), "me ajuda a usar isso aqui" (o roteador ignora) e, nas
  75 originais, "o servidor tá aguentando?" — a ferramenta nova disputa a escolha do modelo.
- Nas 75 originais, 1 fala a menos que antes, por causa das ferramentas extras disputando a escolha.
- **Frases sem "Alexa,"** só funcionam com o modo direto ligado. Com ele desligado, "pausa a música" é ignorada.

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
- **A casa continua simulada** ("acende a luz" não aciona nenhuma lâmpada). A música é real.
- **Biblioteca pequena**: só toca o que existe nas pastas configuradas; não há integração com serviços de música.
- **O player toca no dispositivo de áudio padrão do Windows**, que pode não ser o que você está ouvindo.
- **Um player por servidor**: duas instâncias do laboratório tocariam ao mesmo tempo.

## Verificação ponta a ponta pela API

`bench/phase3_check.py` age como um cliente: ping, 12 falas com desfecho esperado repetidas, ação sensível
(pendente → outro cliente é barrado → o dono confirma → token não vale duas vezes), recusa e confirmação faladas,
timer real cujo aviso tem de chegar pelo stream, stream aberto pelo tempo pedido, e envio de 👍. Resultados em
`runs/phase3/` e em [04-fase3.md](04-fase3.md).

## Como rodar

```bash
THREADS=4 TORCH_THREADS=3 SLOT_DIR=$HOME/decision-lab-data/slots scripts/services.sh start decider-gguf llm-large
LAB_BACKEND=cascade-e5-decider-gguf scripts/lab.sh                      # HOST=0.0.0.0 para o celular
.venv/bin/python tests/test_tools.py                                    # travas (17 testes)
.venv/bin/python -m bench.player_check                                  # toca uns segundos de verdade neste PC
.venv/bin/python -m bench.tools_eval --selectors rules,hybrid,model --scope all --router cascade-e5-decider-gguf
.venv/bin/python -m bench.phase3_check                                  # ciclo completo pela API
curl -s localhost:8000/v1/act -H 'content-type: application/json' -d '{"input": "Alexa, timer de 10 segundos"}'
```

`LAB_TOOL_SELECTOR=rules|model|hybrid` e `LAB_TOOL_SCOPE=route|all` trocam o seletor sem editar `config/backends.yaml`.
