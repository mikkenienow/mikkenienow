# Fase 3 — celular ↔ PC

Estado em 11/10/2026: **o caminho funciona de ponta a ponta** — o celular envia uma fala, recebe a decisão e vê o
resultado de uma ferramenta executada no PC. A verificação automática passou pelo mesmo caminho de rede do celular.
**Falta volume de teste feito por uma pessoa no aparelho** (há 7 falas e nenhum 👍/👎 real), e o p95 ficou um pouco
acima do critério proposto. Fases 4 e 5 continuam aguardando.

## O que existe

- **Interface de celular** (`lab/ui/index.html`): conversa (fala → o que o assistente fez), frases de um toque,
  abas Testar / Casa / Rede / Ajustes, 👍/👎 em cada resposta com a classe certa quando errou.
- **Resultado da ferramenta na tela**: "São 20:19." (real), "Liguei a luz da sala." (simulado), timer que avisa
  sozinho ao terminar (evento do PC, com vibração), anotações gravadas no PC, e **Confirmar / Cancelar** para ações
  sensíveis. Detalhes do ciclo em [05-acoes.md](05-acoes.md).
- **Medição no cliente**: cada fala informa quanto o aparelho esperou (`POST /v1/client_timing`); "Medir rede" faz 20
  idas e voltas vazias; `GET /v1/client_timings` resume por aparelho.
- **Fala opcional das respostas** pela síntese do próprio aparelho (Ajustes → "Falar as respostas").
- **`scripts/phase3_windows.ps1 on|off [-WslIp ip]`**: portproxy + firewall para o WSL2 (administrador).
- **`bench/phase3_check.py`**: um cliente automático que confere o ciclo inteiro pela rede.

## Arquitetura de rede nesta máquina

```
celular (Wi-Fi ou Tailscale) ──► Windows 192.168.1.169:8000 ──portproxy──► WSL2 172.31.160.190:8000 (uvicorn)
                                                                             └─► e5 (em processo) ─► llama-server :8822 (decider GGUF)
```

O WSL2 usa NAT e este Windows (build 22000) não tem a rede "mirrored", então o portproxy é necessário; o IP do WSL
muda a cada reinício da distro.

## Medições

Backend `cascade-e5-decider-gguf`, seletor de ferramenta híbrido. "No servidor" = decisão + escolha da ferramenta + ferramenta.

| cliente e caminho | n | ping p50 | fala → resultado p50 | p95 | no servidor p50 | acréscimo de rede p50 |
|---|---|---|---|---|---|---|
| script, direto no WSL (`localhost`) | 36 | 1,3 ms | 27 ms | 531 ms | 21 ms | ~6 ms |
| **script, pelo caminho do celular** (IP da LAN → portproxy → WSL) | 108 | **44 ms** | **112 ms** | **575 ms** | 22 ms | **90 ms** |
| **celular real** (Android, Chrome, via Tailscale; só decisão, antes das ferramentas) | 7 | não medido | 101 ms | 541 ms | 18 ms | 87 ms |
| navegador no próprio PC | 3 | – | 34 ms | 43 ms | – | 18 ms |

Leituras:

1. **A rede custa ~90 ms por fala, e quase tudo é o portproxy do Windows**, não o Wi-Fi: o mesmo servidor responde em
   1 ms direto e em 44 ms passando pelo portproxy (o script nem sai da máquina). O celular real mediu o mesmo
   acréscimo (87 ms). A causa não foi investigada; 40 ms fixos por requisição é típico de espera de ACK em proxy TCP
   (hipótese). Saídas a testar: rodar um proxy reverso de verdade no Windows, ou o Tailscale dentro do WSL.
2. **O p95 (~550 ms) vem do servidor, não da rede**: é quando a cascata escala ao 2º estágio (~200 ms) e a escolha
   da ferramenta também chama o modelo (~220 ms).
3. **Critério proposto antes** (p50 < 150 ms, p95 < 500 ms, ~100 falas sem erro, stream estável por 10 min):
   p50 ✔ (112 ms) · p95 ✘ por pouco (575 ms) · 108 falas sem erro ✔ · stream aberto 600 s sem cair ✔ (263 eventos).

## Verificação ponta a ponta (`runs/phase3/lan-portproxy.json`)

Rodada pelo caminho do celular, 17 checagens, todas ok:

- servidor responde, modelo carregado, 15 ferramentas, nenhuma de execução de comando;
- **108 de 108 falas** com a ferramenta e o desfecho esperados (hora, data, estado do PC, casa, mídia, anotações,
  duas falas não dirigidas ignoradas, um pedido incompleto que não executa);
- o estado da casa mudou e a anotação foi gravada no PC;
- ação sensível: fica pendente; **outro cliente não consegue confirmar**; o dono confirma e roda; o token não vale duas
  vezes; recusa falada ("não, deixa") cancela; confirmação falada ("sim") executa;
- **timer real**: criado pela API e o aviso chegou pelo stream 2,96 s depois (pedido: 3 s);
- 👍 aceito; stream aberto por 600 s.

O que essa verificação **não** cobre: o toque na tela, o teclado do celular, o Wi-Fi de verdade e o julgamento de uma
pessoa. Na interface, o mesmo fluxo foi exercitado por script no navegador do PC em largura de 390 px (decisão,
ferramenta, botões de confirmação, aviso do timer, abas); não há captura de tela.

## O que o uso real no celular mostrou (11/10, 7 falas ditadas)

| fala | decisão |
|---|---|
| "OK agora eu tô falando vamos ver o que acontece" | ignorar ✔ |
| "E aí a gente não sabe" | ignorar ✔ |
| "Quais são as possibilidades que tem para usar…" | ignorar (era uma pergunta ao assistente?) |
| "mas se eu quisesse que tocasse uma música no…" | ignorar |
| "não quer tocar uma música no Spotify para mim" | **ignorar ✘** (pedido) |
| "é com você Toque uma música no Spotify" | **ignorar ✘** (pedido explícito) |
| "Alex eu Toque uma música no Spotify" | mídia ✔ |

São só 7 falas e sem 👍/👎, mas apontam uma coisa que o dataset escrito não mostrava: **quem usa de verdade fala com
o assistente sem dizer "Alexa"**, e o roteador — treinado numa taxonomia de palavra de ativação — ignora. Numa
interface em que tudo o que se digita é para o assistente, isso é erro. Opções: um modo "tudo é comigo" para clientes
de texto (pular o "é comigo?" e ir direto à escolha da ferramenta), ou ensinar o destinatário com dados do domínio.

## Pendente (precisa de você)

1. **Teste humano com volume**: ~50–100 falas pelo celular marcando 👍/👎 (aba Testar; o placar fica em Ajustes).
   É o único dado de qualidade que não foi escrito por mim.
2. **Olhar a interface no aparelho**: não consegui capturar a tela; teclado aberto e rolagem só se confirmam aí.
3. Fechar a porta quando terminar: `.\scripts\phase3_windows.ps1 off` (administrador). **No momento ela está aberta**
   para a rede local e a tailnet, e a API não tem autenticação.
4. Microfone no celular: exige HTTPS ([06-voz.md](06-voz.md)).

## Como subir

```powershell
# PowerShell como Administrador, em decision-lab; o IP sai de `hostname -I` no WSL
.\scripts\phase3_windows.ps1 on -WslIp 172.31.160.190
```
```bash
# no WSL (abra o WSL pelo Git Bash primeiro se o `wsl` falhar em outros shells)
THREADS=4 TORCH_THREADS=3 SLOT_DIR=$HOME/decision-lab-data/slots scripts/services.sh start decider-gguf llm-large
LAB_BACKEND=cascade-e5-decider-gguf HOST=0.0.0.0 scripts/lab.sh
.venv/bin/python -m bench.phase3_check --base http://192.168.1.169:8000 --sse-seconds 600   # opcional
```

No celular: `http://192.168.1.169:8000/` (Wi-Fi) ou `http://100.105.150.72:8000/` (Tailscale).
