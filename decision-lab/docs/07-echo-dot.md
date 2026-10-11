# Echo Dot — o que dá para integrar, e como

Pesquisa feita em 11/10/2026 na documentação da Amazon (páginas citadas no fim). **Nada foi publicado, criado no
console da Amazon nem exposto à internet.** Onde a documentação lida não cobre um ponto, está escrito "não confirmado".

## Resumo em uma frase

O Echo Dot pode **chamar** o PC (por uma Custom Skill ou uma Smart Home Skill), mas não pode **emprestar o
microfone**: o PC nunca recebe áudio, só texto já interpretado pela Amazon, e só depois de a pessoa falar com a Alexa.

## Três coisas diferentes

| | A. Comando personalizado (Custom Skill) | B. Controle de dispositivos (Smart Home Skill) | C. Microfone contínuo / trocar a voz da Alexa |
|---|---|---|---|
| Como a pessoa fala | "Alexa, **pede para o \<nome\>** acender a luz" ou "Alexa, abre o \<nome\>" | "Alexa, acende a luz da sala" (sem nome de skill) | falar livremente, sem "Alexa" |
| Quem entende a fala | a Amazon (ASR + NLU); a skill recebe intenção e slots em texto | a Amazon; a skill recebe diretivas (`TurnOn`, `Discover`…) | — |
| O PC recebe | JSON com a intenção e, com `AMAZON.SearchQuery`, a frase livre em texto | JSON com a diretiva e o id do dispositivo | **nada: não existe** |
| Onde roda o código | AWS Lambda **ou** um serviço HTTPS seu | **AWS Lambda obrigatório** ("You host your add-on code on AWS Lambda") | — |
| Conta/vínculo | conta de desenvolvedor Amazon (gratuita) | + conta AWS + **account linking OAuth 2.0 obrigatório** | — |
| Serve para testar o roteador? | **sim**: a frase livre passa pelo roteador e pelas ferramentas | pouco: a Alexa já escolheu a ação; o roteador não decide nada | era o cenário original do experimento; **não é viável no Echo** |
| Viável com o PC como backend? | **sim** | sim, com o Lambda só repassando para o PC | **não** |

### A. Custom Skill

- A skill recebe **texto**, não áudio. A referência do JSON de requisição não tem campo de áudio; um estudo do
  ecossistema de skills (PETS 2017) afirma que o áudio não é disponibilizado a desenvolvedores.
- **Frase livre**: o tipo de slot `AMAZON.SearchQuery` captura "a search query like you might enter into a search
  engine" e **suporta Português (BR)**. Restrições: toda frase de exemplo precisa de uma **frase portadora**
  (palavras fora do slot, ex.: "pergunta {frase}"), no máximo **um** `SearchQuery` por intenção, e ele não pode ser
  combinado com outro slot na mesma frase de exemplo.
- **Endpoint HTTPS próprio** (alternativa ao Lambda) — requisitos da Amazon:
  - acessível pela internet, **porta 443**, TLS com certificado confiável pela Amazon e o domínio no *Subject
    Alternative Names*; no console há três opções: CA confiável, curinga de subdomínio, ou **autoassinado só para teste**;
  - **verificar que a requisição veio da Alexa**: cabeçalhos `Signature-256` e `SignatureCertChainUrl` (a URL tem de
    ser `https://s3.amazonaws.com/echo.api/…`, porta 443; o certificado precisa ter `echo-api.amazon.com` no SAN,
    estar válido e encadear a uma raiz confiável; a assinatura é conferida contra o SHA-256 do corpo) e **timestamp
    dentro de 150 s**; falhou → `400`. Os SDKs oficiais (Python/Node/Java) fazem isso.
  - conferir o `applicationId` (o id da skill) da requisição: a referência diz que ele serve "to verify that the
    request was intended for your service".
- **Limites da resposta**: fala de até 8 000 caracteres, resposta de até 120 KB. Com `shouldEndSession: false` a
  Alexa "opens the microphone for a few seconds" para a resposta; não há escuta contínua.
- **Tempo máximo para responder**: não está nas páginas lidas (**não confirmado**; o valor citado em fóruns é ~8 s).
  Importa porque o LLM local leva 3–10 s nesta máquina.
- **Teste sem publicar**: o console tem um estágio "Development"; a página de testes diz que "the Alexa app shows
  published skills, as well as your own skills under development". O uso no Echo físico da mesma conta **não está
  explícito** nessa página (não confirmado; é o comportamento normalmente descrito).

### B. Smart Home Skill

- Vantagem: fala natural ("Alexa, acende a luz da sala") e o dispositivo aparece no app da Alexa.
- Exigências: conta AWS, função **Lambda** (não há opção de endpoint HTTPS próprio na página de construção),
  **account linking obrigatório** com OAuth 2.0 *authorization code* (pode ser Login with Amazon).
- O Lambda recebe `Alexa.Discovery/Discover`, `Alexa.PowerController/TurnOn|TurnOff`, `Alexa.Authorization/AcceptGrant`
  e precisaria repassar ao PC por HTTPS público.
- Só cobre o que as interfaces de dispositivo modelam (ligar, desligar, brilho, termostato…). Hora, anotações e
  perguntas não cabem aqui.
- Região do Lambda para pt-BR: não coberto na página lida (não confirmado).

### C. Microfone contínuo, palavra de ativação própria, substituir a Alexa

Não há API para isso num Echo: a palavra de ativação, o reconhecimento de fala e a voz são da Amazon. O Alexa Voice
Service (AVS) serve para colocar a Alexa **no seu** hardware, não para usar o hardware do Echo com outro assistente.
**Consequência para este projeto**: o cenário "ouvir a casa o tempo todo e decidir se é comigo" — que é onde o
roteador tem mais valor e mais risco — precisa de **um microfone nosso** (PC, celular ou um satélite ESP32/Raspberry).
Isso é a Fase 4 ([06-voz.md](06-voz.md)), não o Echo.

## O que muda no papel do roteador

No Echo (opção A) o problema difícil do experimento — "essa fala é comigo?" — já chega resolvido: a pessoa disse
"Alexa, pede para o \<nome\>…". Sobra para o PC a parte em que o laboratório vai bem: escolher a ação certa para um
texto livre (88% ponta a ponta, [05-acoes.md](05-acoes.md)) e aplicar as travas (lista fechada, validação, confirmação).

## Integração mínima proposta (opção A, PC como backend)

```
"Alexa, pede para o laboratório acender a luz da sala"
   Echo Dot ─► nuvem da Alexa (ASR, pt-BR)
            ─► Custom Skill em desenvolvimento, 1 intenção:  CatchAllIntent { frase: AMAZON.SearchQuery }
                 exemplos: "para {frase}", "que {frase}", "pra {frase}", "se {frase}"   (frase portadora obrigatória)
            ─► HTTPS 443  https://<pc>/alexa      (túnel público até o PC)
   PC:  adaptador /alexa
          1. valida assinatura, timestamp (150 s) e applicationId      → senão 400
          2. POST /v1/act {input: frase, client: <userId da Alexa>}     (o mesmo ciclo já testado)
          3. tool.say  → resposta em JSON para a Alexa falar
          4. needs_confirmation → shouldEndSession:false + "Confirma?"; AMAZON.YesIntent/NoIntent → /v1/act/confirm
```

Trabalho no repositório (estimativa: 1 dia): um endpoint `/alexa` (~150 linhas, com `ask-sdk-webservice-support` para a
verificação), o modelo de interação em JSON (pt-BR) e testes com requisições de exemplo gravadas. Tudo isso roda e
se testa **offline**, antes de qualquer conta.

### Como o PC fica acessível por HTTPS público

| Opção | Custo | O que exige | Observações |
|---|---|---|---|
| **Tailscale Funnel** (recomendada: o Tailscale já está instalado) | gratuito ("available for all plans") | no painel: MagicDNS (já ativo), **HTTPS Certificates** (hoje desligado) e o atributo `funnel` na política | portas públicas 443/8443/10000; nome fixo `desktop-ugncll1.tail63a6b8.ts.net`; sem domínio próprio; limite de banda não divulgado. Certificado emitido para o nome `ts.net` (aparentemente Let's Encrypt; **confirmar** que a Alexa aceita — no console seria a opção "CA confiável") |
| Cloudflare Tunnel | gratuito | um domínio seu na Cloudflare | certificado da Cloudflare, domínio próprio |
| Lambda como ponte (ou skill *Alexa-hosted*) | camada gratuita da AWS | conta AWS (ou só a de desenvolvedor, no Alexa-hosted) | o Lambda ainda precisa alcançar o PC: não elimina o túnel |

Regra de segurança para qualquer opção: publicar **só o caminho `/alexa`**, que rejeita tudo que não tenha
assinatura válida da Amazon. A API do laboratório (`/v1/*`) não tem autenticação e não pode ir para a internet.

### Limitações já conhecidas dessa integração

1. **Sempre com nome de invocação** ("pede para o …"). Fala natural sem nome só na opção B, e só para dispositivos.
2. **Sem avisos espontâneos**: o Echo não fala quando um timer nosso termina. Há APIs de notificação (anel amarelo)
   que não foram investigadas; o natural é deixar timers com a própria Alexa.
3. **Respostas do LLM local** (3–10 s aqui) podem estourar o tempo da skill; começaria só com as ferramentas
   rápidas (dezenas de ms) e uma resposta "isso eu ainda não sei responder por aqui" para o resto.
4. **Duas camadas de erro de transcrição**: a ASR da Amazon e a frase portadora cortando o começo da fala.
5. **Privacidade**: a fala passa pela nuvem da Amazon de qualquer jeito; só a decisão e a ação ficam locais.

## O que depende de você (credenciais, autorização, hardware)

- Conta de desenvolvedor Amazon **com o mesmo login do Echo Dot** (gratuita) e criar a skill em pt-BR no console.
- Autorizar a exposição pública do `/alexa` e ligar HTTPS + Funnel no painel do Tailscale.
- Conta AWS só se for pela opção B ou por Lambda.
- O Echo Dot na mão para o teste final.

## Fontes

- [Host a Custom Skill as a Web Service](https://developer.amazon.com/en-US/docs/alexa/custom-skills/host-a-custom-skill-as-a-web-service.html) — requisitos do endpoint e verificação da requisição
- [Slot Type Reference](https://developer.amazon.com/en-US/docs/alexa/custom-skills/slot-type-reference.html) — `AMAZON.SearchQuery`, idiomas e restrições
- [Request and Response JSON Reference](https://developer.amazon.com/en-US/docs/alexa/custom-skills/request-and-response-json-reference.html) — limites, `shouldEndSession`, `applicationId`
- [Steps to Build a Smart Home Skill](https://developer.amazon.com/en-US/docs/alexa/smarthome/steps-to-build-a-smart-home-skill.html) — Lambda e account linking obrigatórios
- [Requirements for Account Linking](https://developer.amazon.com/docs/account-linking/requirements-account-linking.html)
- [Test Your Skill](https://developer.amazon.com/en-US/docs/alexa/devconsole/test-your-skill.html) — estágio de desenvolvimento
- [Deprecated Features](https://developer.amazon.com/en-US/docs/alexa/ask-overviews/deprecated-features.html) — remoções de 2026 (Routines Kit, skills automotivas); nada sobre custom ou smart home skills
- [Amazon Alexa Skills Ecosystem Privacy (PETS 2017)](https://www.petsymposium.org/2017/papers/hotpets/amazon-alexa-skills-ecosystem-privacy.pdf) — o áudio não vai para o desenvolvedor
- [Tailscale Funnel](https://tailscale.com/kb/1223/funnel)

Não encontrei documentação sobre como o Alexa+ trata custom skills em pt-BR; vale conferir no console antes de começar.
