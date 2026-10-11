# Voz — o que existe hoje e o que falta para ligar a fala ao roteador

Revisão feita em 11/10/2026. Esta etapa é só de preparação: **nenhum STT nem VAD foi implementado ou medido aqui.**
Os números de latência de fala abaixo são orçamento, não medição.

## O que existe no repositório

| Peça | Estado | Onde |
|---|---|---|
| Captura de áudio | **não existe** no servidor. Não há endpoint que receba áudio | — |
| VAD (detectar onde a fala começa e termina) | **não existe** | — |
| STT local (whisper.cpp ou outro) | **não existe**; nada instalado em `vendor/` | — |
| STT pelo navegador | prévia: botão 🎤 usa a Web Speech API do Chrome | `lab/ui/index.html` |
| Saída de voz | prévia nova: "Falar as respostas" (síntese do próprio aparelho, `speechSynthesis`) | `lab/ui/index.html`, aba Ajustes |
| Entrada de texto → decisão → ação | **pronto e testado**: `POST /v1/act {input, client, source}` | `lab/server.py`, `lab/actions.py` |

Limitações da prévia de STT do navegador, que impedem tratá-la como "voz do projeto":

1. **Só funciona em HTTPS ou `localhost`.** No celular, por `http://192.168.x.x`, o Chrome bloqueia o microfone; a
   UI esconde o botão. Foi o que aconteceu no teste de 11/10 ("fico falando e nada acontece").
2. **Não é local**: o Chrome envia o áudio para o serviço de voz do Google.
3. **Sem controle**: não dá para medir latência por etapa, ver a confiança da transcrição nem trocar o modelo.
4. **Não é escuta contínua de verdade**: precisa de toque para começar e o navegador encerra a sessão sozinho.

## O que o roteador já sabe sobre texto vindo de fala

- Estabilidade à fala "crua" (minúsculas, sem acento, sem pontuação): 85–94% das decisões se mantêm
  ([03-resultados.md](03-resultados.md)).
- Fatia `asr` do teste (erros de transcrição escritos à mão, 13 falas): 69–77% no decider/Jeff, 77% no e5-logreg.
- **Erros reais de ASR nunca foram medidos**: o dataset foi digitado. É o maior ponto cego antes de ligar voz.
- Em escuta contínua o roteador vê **todas** as falas da casa. Com 7,5% de falsa ativação na cascata, uma conversa de
  100 falas dispara ~7 ações indevidas. As travas do adaptador limitam o dano (ações sensíveis pedem confirmação),
  mas luz e música simuladas hoje seriam luz e música de verdade amanhã.

## Trabalho necessário, em ordem

| # | Tarefa | Por quê | Esforço |
|---|---|---|---|
| 1 | **HTTPS para o celular** (`tailscale serve`, depois de ligar "HTTPS Certificates" no painel) | sem isso o navegador do celular não entrega microfone | 30 min, precisa de você no painel |
| 2 | **Medir o STT nesta CPU**: whisper.cpp `base` e `small` em pt, 3–4 threads; tempo por segundo de áudio e taxa de erro em ~30 frases gravadas | decide se o STT cabe no orçamento; a CPU já é disputada (decider, LLM) e usar todos os núcleos piora tudo ([02-ambiente.md](02-ambiente.md)) | meio dia |
| 3 | **Endpoint de áudio** `POST /v1/utterance` (WAV/Opus de uma fala) → STT → `/v1/act` com `source: "voice"`; registrar `stt_ms`, texto e confiança da transcrição no log | é o ponto único de entrada de fala, igual para celular, PC e um satélite futuro | 1 dia |
| 4 | **VAD no cliente** (Silero VAD em ONNX/WASM no navegador, ou `webrtcvad` num cliente nativo): cortar em falas e só enviar quando houver voz | sem VAD o STT transcreve silêncio e TV; define também a latência de "fim de fala" (300–500 ms de silêncio) | 1–2 dias |
| 5 | **Filtro antes do roteador**: descartar transcrição vazia, muito curta ou com confiança baixa (`no_speech_prob` do Whisper) | o Whisper "inventa" frases em ruído; isso viraria falsa ativação | meio dia |
| 6 | **Medir de verdade**: gravar 100–200 falas (dirigidas e não dirigidas, 2+ pessoas), passar pelo pipeline inteiro e repetir as métricas (falsa ativação, perdidos, latência por etapa) | substitui o dataset digitado; valida os limiares | 1–2 dias, precisa das gravações |
| 7 | **Destinatário**: palavra de ativação barata na frente (openWakeWord) e/ou fine-tuning do e5 com exemplos do domínio | é o problema nº 1 do experimento e fica pior com escuta contínua | à parte |
| 8 | **Saída de voz local** (Piper) se a síntese do navegador não bastar | opcional; a prévia já fala pelo aparelho | meio dia |

Onde fica o microfone é uma decisão de hardware: **celular** (mais rápido de testar, depende do item 1), **PC**
(microfone no Windows; o áudio dentro do WSL2 é instável, então a captura teria de ser um processo nativo do Windows
enviando para o item 3) ou um **satélite** dedicado (ESP32-S3/Raspberry) mais adiante. O Echo Dot **não** serve como
microfone ([07-echo-dot.md](07-echo-dot.md)).

## Orçamento de latência (a confirmar no item 2)

| Etapa | Estimativa | Base |
|---|---|---|
| fim de fala (VAD) | 300–500 ms | parâmetro de silêncio |
| STT | **não medido** | depende do item 2 |
| roteador | ~20 ms (estágio 1) a ~220 ms (escalou) | medido |
| escolha da ferramenta | 0 ms (regra) a ~220 ms (modelo) | medido |
| ferramenta | < 1 ms | medido |
| rede celular ↔ PC | ~90 ms de acréscimo | medido em 7 falas no celular |

## Contrato já pronto para a voz

Qualquer cliente de fala só precisa entregar texto:

```http
POST /v1/act
{"input": "acende a luz da sala", "client": "<id estável do aparelho>", "source": "voice"}
```

A resposta traz `tool.say` (frase para falar), `tool.status` e, se for ação sensível, `tool.confirm.token`.
A confirmação pode ser por `POST /v1/act/confirm` ou **falada**: a próxima fala do mesmo `client` ("sim", "não,
deixa", "cancela") é tratada como resposta, sem passar pelo roteador.
