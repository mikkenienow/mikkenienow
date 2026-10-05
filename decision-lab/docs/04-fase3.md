# Fase 3 — celular ↔ PC

Estado em 04/10/2026: **instrumentação pronta e medida a partir do host Windows; falta a medição com o celular**,
que depende de (a) abrir a porta 8000 do PC para a rede local (ação de administrador, API sem autenticação) e
(b) do aparelho. Fases 4 e 5 continuam bloqueadas até esta estar estável.

## O que foi feito

- **Medição no cliente.** A UI agora cronometra cada fala enviada (`performance.now()` em volta do `POST /v1/route`)
  e informa ao servidor (`POST /v1/client_timing`). A diferença entre a ida-e-volta vista pelo dispositivo e o
  `latency_ms` da decisão é o custo de rede + servidor. Cada entrada do feed mostra
  `ida e volta neste dispositivo: X ms (decisão Y ms + Z ms de rede/servidor)`.
- **Botão "📶 medir rede"**: 20 `GET /health` (sem modelo) para medir só a rede.
- **Painel "Rede (por dispositivo)"** e `GET /v1/client_timings`: p50/p95 de ida-e-volta e de acréscimo, por IP do
  cliente e tipo (`ping` / `route`). Tudo também vai para `runs/decisions.jsonl` (`type: client_timing`).
- **`scripts/phase3_windows.ps1 on|off`**: portproxy + regra de firewall (perfil Privado) para o caso WSL2.

## Arquitetura de rede nesta máquina

```
celular (Wi-Fi) ──► PC Windows 192.168.1.169:8000 ──portproxy──► WSL2 172.31.x.x:8000 (uvicorn, HOST=0.0.0.0)
                                                                    └─► e5 (em processo) ─► llama-server :8822 (decider GGUF)
```

O WSL2 usa NAT; o Windows 11 build 22000 não tem o modo de rede "mirrored" (exige 22H2+), então o portproxy é
necessário. O IP do WSL muda a cada reinício da distro (rodar `on` de novo).

## Medido até agora (cliente = host Windows, fora do WSL; backend `cascade-e5-decider-gguf`)

| caminho | ping p50 | fala → resposta p50 | decisão p50 | acréscimo p50 | fala → resposta p95 |
|---|---|---|---|---|---|
| Windows → `localhost:8000` (encaminhamento do WSL) | 2,1 ms | 28 ms | 21 ms | 7 ms | 385 ms |
| Windows → IP do WSL (rede virtual Hyper-V) | 1,8 ms | 27 ms | 21 ms | 7 ms | 330 ms |
| navegador (Chrome no Windows, UI) | 2 ms | ~33 ms | 15 ms | ~18 ms | – |

Leitura: o servidor acrescenta ~5–7 ms à decisão (JSON, log em arquivo, roteamento, executor simulado); a rede
virtual, ~2 ms. O p95 é dominado pela cascata escalando ao 2º estágio (~200–350 ms), não pela rede. Numa rede
Wi-Fi doméstica espera-se +2–10 ms de ida-e-volta (a medir).

## Como concluir (precisa de você)

```powershell
# PowerShell como Administrador, na pasta decision-lab
.\scripts\phase3_windows.ps1 on        # mostra o endereço para abrir no celular
```
```bash
# no WSL
THREADS=4 TORCH_THREADS=3 SLOT_DIR=$HOME/decision-lab-data/slots scripts/services.sh start decider-gguf llm-large
HOST=0.0.0.0 scripts/lab.sh
```

No celular (mesma rede Wi-Fi): abrir `http://192.168.1.169:8000/`, escolher o backend, tocar em **📶 medir rede**,
depois em **▶ stream de demonstração** e enviar algumas falas à mão. Os números aparecem no painel "Rede" e em
`GET /v1/client_timings`. Ao terminar: `.\scripts\phase3_windows.ps1 off`.

Critério de "estável" para liberar a Fase 4: ida-e-volta p50 de comando < 150 ms e p95 < 500 ms no celular, sem
erros em ~100 falas, e o SSE (feed em tempo real) sem cair por 10 minutos.

Observação para a Fase 4: o microfone no navegador do celular (`getUserMedia` / Web Speech API) exige **HTTPS**
fora de `localhost`. Será preciso um certificado local (ex.: `tailscale serve`, já que a máquina tem Tailscale, ou
mkcert) antes de capturar áudio no celular.
