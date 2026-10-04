## Resultado principal (159 falas, taxonomia de 6 classes)

| backend | grupo | acurácia | falsa ativação | pedidos perdidos | intenção (se ativado) | p50 | p95 | CPU-s/decisão | ECE | AUROC conf. | estabilidade* |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `decider-0.8b-gguf-restore` | C) decisão | 78.6% | 37.7% | 6.1% | 91.4% | 204 ms | 314 ms | 0.79 | 0.07 | 0.81 | 89.3% |
| `decider-0.8b-schema` | C) decisão | 78.6% | 37.7% | 6.1% | 91.4% | 350 ms | 438 ms | 1.14 | 0.02 | 0.81 | 88.7% |
| `decider-0.8b-gguf` | C) decisão | 78.6% | 37.7% | 6.1% | 91.4% | 1427 ms | 1623 ms | 5.90 | 0.06 | 0.81 | 89.9% |
| `jeff-0.8b` | C) decisão | 79.2% | 45.3% | 4.0% | 94.7% | 2802 ms | 3126 ms | 7.74 | 0.10 | 0.75 | 88.1% |
| `jeff-0.8b-pt` | C) decisão | 82.4% | 37.7% | 2.0% | 93.8% | 2864 ms | 3248 ms | 8.18 | 0.16 | 0.70 | 90.6% |
| `qwen3.5-0.8b-logprob` | D) LLM genérico (logprob) | 46.5% | 83.0% | 4.0% | 64.2% | 1910 ms | 2210 ms | 7.70 | 0.15 | 0.74 | 81.1% |
| `qwen3.5-4b-chat` | A) LLM generativo | 88.7% | 28.3% | 0.0% | 98.0% | 10340 ms | 11890 ms | 43.53 | 0.07 | 0.80 | 93.7% |
| `e5-logreg` | B) treinado | 86.8% | 11.3% | 2.0% | 86.6% | 17 ms | 28 ms | 0.05 | 0.42 | 0.89 | 85.5% |

\* concordância da decisão entre a fala original e a mesma fala sem acentos/pontuação/maiúsculas.

## Acurácia por fatia (tags)

| backend | clear | hard | ambiguous | short | long | asr | no_wake | mentions_wake | near_wake | background | to_human | english |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `decider-0.8b-gguf-restore` | 91.2% | 35.7% | 90.9% | 89.5% | 66.7% | 69.2% | 88.9% | 33.3% | 50.0% | 60.0% | 61.5% | 100.0% |
| `decider-0.8b-schema` | 91.2% | 35.7% | 90.9% | 89.5% | 66.7% | 69.2% | 88.9% | 33.3% | 50.0% | 60.0% | 61.5% | 100.0% |
| `decider-0.8b-gguf` | 91.2% | 35.7% | 90.9% | 89.5% | 66.7% | 69.2% | 88.9% | 33.3% | 50.0% | 60.0% | 61.5% | 100.0% |
| `jeff-0.8b` | 90.1% | 39.3% | 81.8% | 78.9% | 100.0% | 69.2% | 88.9% | 50.0% | 50.0% | 20.0% | 46.2% | 100.0% |
| `jeff-0.8b-pt` | 91.2% | 42.9% | 100.0% | 89.5% | 88.9% | 76.9% | 88.9% | 33.3% | 100.0% | 20.0% | 61.5% | 100.0% |
| `qwen3.5-0.8b-logprob` | 51.6% | 25.0% | 54.5% | 52.6% | 22.2% | 46.2% | 55.6% | 16.7% | 0.0% | 0.0% | 7.7% | 80.0% |
| `qwen3.5-4b-chat` | 93.4% | 60.7% | 90.9% | 100.0% | 88.9% | 100.0% | 66.7% | 66.7% | 100.0% | 80.0% | 46.2% | 100.0% |
| `e5-logreg` | 93.4% | 78.6% | 90.9% | 84.2% | 55.6% | 76.9% | 100.0% | 16.7% | 100.0% | 80.0% | 100.0% | 100.0% |

N por fatia: clear=91, hard=28, ambiguous=11, short=19, long=9, asr=13, no_wake=9, mentions_wake=6, near_wake=2, background=5, to_human=13, english=5

## Acurácia por classe

| backend | complex | home_control | ignore | knowledge | media | timer_alarm |
|---|---|---|---|---|---|---|
| `decider-0.8b-gguf-restore` | 73.3% | 84.4% | 65.5% | 100.0% | 94.4% | 73.3% |
| `decider-0.8b-schema` | 73.3% | 84.4% | 65.5% | 100.0% | 94.4% | 73.3% |
| `decider-0.8b-gguf` | 73.3% | 84.4% | 65.5% | 100.0% | 94.4% | 73.3% |
| `jeff-0.8b` | 93.3% | 90.6% | 58.6% | 95.2% | 94.4% | 80.0% |
| `jeff-0.8b-pt` | 93.3% | 93.8% | 65.5% | 90.5% | 100.0% | 80.0% |
| `qwen3.5-0.8b-logprob` | 53.3% | 93.8% | 20.7% | 57.1% | 33.3% | 40.0% |
| `qwen3.5-4b-chat` | 93.3% | 100.0% | 72.4% | 95.2% | 100.0% | 100.0% |
| `e5-logreg` | 100.0% | 87.5% | 89.7% | 85.7% | 77.8% | 73.3% |

## Economia de LLM (rotas knowledge/complex)

| backend | chamadas ao LLM | evitadas vs. mandar tudo | necessárias | perdidas | desperdiçadas |
|---|---|---|---|---|---|
| `decider-0.8b-gguf-restore` | 49/159 | 69.2% | 36 | 3 | 13 |
| `decider-0.8b-schema` | 49/159 | 69.2% | 36 | 3 | 13 |
| `decider-0.8b-gguf` | 49/159 | 69.2% | 36 | 3 | 13 |
| `jeff-0.8b` | 46/159 | 71.1% | 36 | 3 | 10 |
| `jeff-0.8b-pt` | 40/159 | 74.8% | 36 | 4 | 5 |
| `qwen3.5-0.8b-logprob` | 28/159 | 82.4% | 36 | 16 | 6 |
| `qwen3.5-4b-chat` | 46/159 | 71.1% | 36 | 2 | 8 |
| `e5-logreg` | 44/159 | 72.3% | 36 | 1 | 8 |

## Limiar de confiança (política: abaixo do limiar → ignorar)

- `decider-0.8b-gguf-restore`: τ=0.00: acc 78.6%, FA 37.7%, perdidos 6.1% · τ=0.50: acc 79.9%, FA 32.1%, perdidos 11.1% · τ=0.70: acc 78.0%, FA 18.9%, perdidos 25.3% · τ=0.90: acc 67.9%, FA 7.5%, perdidos 47.5%
- `decider-0.8b-schema`: τ=0.00: acc 78.6%, FA 37.7%, perdidos 6.1% · τ=0.50: acc 78.6%, FA 35.8%, perdidos 11.1% · τ=0.70: acc 77.4%, FA 18.9%, perdidos 25.3% · τ=0.90: acc 69.2%, FA 5.7%, perdidos 46.5%
- `decider-0.8b-gguf`: τ=0.00: acc 78.6%, FA 37.7%, perdidos 6.1% · τ=0.50: acc 79.9%, FA 32.1%, perdidos 11.1% · τ=0.70: acc 78.0%, FA 18.9%, perdidos 25.3% · τ=0.90: acc 67.9%, FA 7.5%, perdidos 47.5%
- `jeff-0.8b`: τ=0.00: acc 79.2%, FA 45.3%, perdidos 4.0% · τ=0.50: acc 79.9%, FA 24.5%, perdidos 16.2% · τ=0.70: acc 79.2%, FA 13.2%, perdidos 26.3% · τ=0.90: acc 69.2%, FA 9.4%, perdidos 44.4%
- `jeff-0.8b-pt`: τ=0.00: acc 82.4%, FA 37.7%, perdidos 2.0% · τ=0.50: acc 83.6%, FA 22.6%, perdidos 11.1% · τ=0.70: acc 79.9%, FA 17.0%, perdidos 23.2% · τ=0.90: acc 67.9%, FA 13.2%, perdidos 44.4%
- `qwen3.5-0.8b-logprob`: τ=0.00: acc 46.5%, FA 83.0%, perdidos 4.0% · τ=0.50: acc 52.2%, FA 54.7%, perdidos 24.2% · τ=0.70: acc 51.6%, FA 11.3%, perdidos 71.7% · τ=0.90: acc 39.6%, FA 0.0%, perdidos 97.0%

## Custo e memória

| backend | modelo | CPU-s/decisão | núcleos ocupados | RSS servidor | carga |
|---|---|---|---|---|---|
| `decider-0.8b-gguf-restore` | Mapika/decider-0.8b (GGUF Q8_0, llama.cpp, prefixo restaurado de arquivo) | 0.787 | 3.7 | 1025 MB | 1.4 s |
| `decider-0.8b-schema` | Mapika/decider-0.8b (PyTorch CPU, schema cache) | 1.140 | 3.1 | 3489 MB | 0.7 s |
| `decider-0.8b-gguf` | Mapika/decider-0.8b (GGUF Q8_0, llama.cpp, sem cache de prefixo) | 5.895 | 4.1 | 1009 MB | 0.7 s |
| `jeff-0.8b` | mstrasser/Jeff-Qwen3.5-0.8B@v1.2 (PyTorch fp32, CPU) | 7.741 | 2.8 | 3899 MB | 0.7 s |
| `jeff-0.8b-pt` | mstrasser/Jeff-Qwen3.5-0.8B@v1.2 (PyTorch fp32, CPU) | 8.184 | 2.8 | 3903 MB | 0.7 s |
| `qwen3.5-0.8b-logprob` | Qwen/Qwen3.5-0.8B (GGUF Q8_0, llama.cpp) - sem especialização | 7.698 | 4.0 | 1012 MB | 0.8 s |
| `qwen3.5-4b-chat` | Qwen/Qwen3.5-4B (GGUF Q4_K_M) | 43.529 | 4.2 | 4363 MB | 0.9 s |
| `e5-logreg` | intfloat/multilingual-e5-small | 0.052 | 2.8 | +903 (no processo do lab) MB | 48.5 s |

## Escalonamento de intenções (classes definidas na requisição; 60 falas)

| backend | cenário | opções | acurácia | falsa ativação | perdidos | escolheu distrator | p50 |
|---|---|---|---|---|---|---|---|
| `decider-0.8b-schema` | gate | 2 | 76.7% | 63.2% | 5.3% | 0.0% | 511 ms |
| `decider-0.8b-schema` | n6 | 6 | 80.0% | 26.3% | 10.5% | 0.0% | 522 ms |
| `decider-0.8b-schema` | n12 | 12 | 81.7% | 26.3% | 10.5% | 0.0% | 492 ms |
| `decider-0.8b-schema` | n20 | 20 | 81.7% | 26.3% | 10.5% | 0.0% | 493 ms |
| `decider-0.8b-schema` | n32 | 32 | 76.7% | 21.1% | 15.8% | 5.0% | 456 ms |
| `jeff-0.8b` | gate | 2 | 60.0% | 10.5% | 57.9% | 0.0% | 1902 ms |
| `jeff-0.8b` | n6 | 6 | 76.7% | 36.8% | 7.9% | 0.0% | 2741 ms |
| `jeff-0.8b` | n12 | 12 | 71.7% | 52.6% | 7.9% | 8.3% | 4045 ms |
| `jeff-0.8b` | n20 | 20 | 70.0% | 57.9% | 7.9% | 13.3% | 4136 ms |
| `jeff-0.8b` | n32 | 32 | 63.3% | 68.4% | 7.9% | 18.3% | 5364 ms |
| `decider-0.8b-gguf-restore` | gate | 2 | 76.7% | 63.2% | 5.3% | 0.0% | 234 ms |
| `decider-0.8b-gguf-restore` | n6 | 6 | 80.0% | 26.3% | 10.5% | 0.0% | 198 ms |
| `decider-0.8b-gguf-restore` | n12 | 12 | 81.7% | 26.3% | 10.5% | 0.0% | 222 ms |
| `decider-0.8b-gguf-restore` | n20 | 20 | 81.7% | 26.3% | 10.5% | 0.0% | 236 ms |
| `decider-0.8b-gguf-restore` | n32 | 32 | 76.7% | 21.1% | 15.8% | 5.0% | 237 ms |

## Fase 2 — router na frente do LLM (ponta a ponta pela API)

| estratégia | falas | tempo total | só decisões | só LLM | chamadas LLM | necessárias | desperdiçadas | perdidas | falsa ativação |
|---|---|---|---|---|---|---|---|---|---|
| none (tudo -> LLM 2B) | 80 | 193 s | 0 s | 193 s | 80 | 18 | 62 | 0 | 100.0% |
| cascade-e5-decider τ=0.0 | 80 | 119 s | 6 s | 113 s | 20 | 18 | 2 | 0 | 3.7% |
| decider-0.8b-schema τ=0.0 | 80 | 130 s | 32 s | 98 s | 24 | 18 | 5 | 0 | 25.9% |
| qwen3.5-4b-chat τ=0.0 | 80 | 1011 s | 881 s | 129 s | 23 | 18 | 5 | 1 | 25.9% |
| cascade-e5-decider-gguf τ=0.0 | 80 | 128 s | 6 s | 122 s | 20 | 18 | 2 | 0 | 3.7% |
