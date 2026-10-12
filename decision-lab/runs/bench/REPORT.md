## Resultado principal (159 falas, taxonomia de 6 classes)

| backend | grupo | acurácia | falsa ativação | pedidos perdidos | intenção (se ativado) | p50 | p95 | CPU-s/decisão | ECE | AUROC conf. | estabilidade* |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `julia-1` | C) decisão | 34.6% | 100.0% | 0.0% | 53.5% | 177 ms | 309 ms | 0.83 | 0.49 | 0.66 | 73.0% |
| `julia-1-pt` | C) decisão | 26.4% | 92.5% | 17.2% | 43.9% | 188 ms | 250 ms | 0.77 | 0.45 | 0.65 | 66.0% |
| `decider-0.8b-schema` | C) decisão | 78.6% | 37.7% | 6.1% | 91.4% | 542 ms | 633 ms | 2.15 | 0.02 | 0.81 | 88.7% |
| `decider-0.8b-schema-pt` | C) decisão | 75.5% | 58.5% | 3.0% | 94.8% | 542 ms | 623 ms | 2.15 | 0.10 | 0.79 | 88.7% |
| `laya` | C) decisão | 40.9% | 67.9% | 7.1% | 48.9% | 1100 ms | 1304 ms | 4.32 | 0.15 | 0.64 | 74.2% |
| `jeff-0.8b` | C) decisão | 79.2% | 45.3% | 4.0% | 94.7% | 3051 ms | 3278 ms | 7.32 | 0.10 | 0.75 | 88.1% |
| `jeff-0.8b-pt` | C) decisão | 82.4% | 37.7% | 2.0% | 93.8% | 3072 ms | 3308 ms | 7.50 | 0.16 | 0.70 | 90.6% |
| `jeff-0.8b-gate` | C) decisão | 79.9% | 17.0% | 21.2% | 97.4% | 5124 ms | 5552 ms | 12.62 | 0.15 | 0.71 | – |
| `qwen3.5-0.8b-logprob` | D) LLM genérico (logprob) | 47.8% | 83.0% | 4.0% | 66.3% | 2040 ms | 2313 ms | 7.78 | 0.13 | 0.71 | 78.6% |
| `qwen3.5-0.8b-chat` | A) LLM generativo | 37.1% | 100.0% | 0.0% | 57.6% | 2598 ms | 2850 ms | 9.93 | 0.37 | 0.75 | 93.1% |
| `qwen3.5-2b-chat` | A) LLM generativo | 77.4% | 58.5% | 0.0% | 96.0% | 3582 ms | 3841 ms | 13.95 | 0.06 | 0.79 | 91.2% |
| `qwen3.5-4b-chat` | A) LLM generativo | 88.1% | 28.3% | 1.0% | 98.0% | 8644 ms | 9131 ms | 33.28 | 0.06 | 0.81 | – |
| `nli-mdeberta` | zero-shot | 27.7% | 92.5% | 7.1% | 39.1% | 1102 ms | 1234 ms | 4.35 | 0.09 | 0.68 | 44.0% |
| `gliclass-edge` | zero-shot | 44.0% | 96.2% | 1.0% | 64.3% | 98 ms | 127 ms | 0.40 | 0.23 | 0.74 | 76.7% |
| `e5-zeroshot` | zero-shot | 28.9% | 75.5% | 69.7% | 96.7% | 24 ms | 35 ms | 0.10 | – | 0.64 | 73.6% |
| `tfidf-logreg` | B) treinado | 78.0% | 30.2% | 6.1% | 86.0% | 2 ms | 3 ms | 0.00 | 0.19 | 0.80 | 95.0% |
| `e5-logreg` | B) treinado | 86.8% | 11.3% | 2.0% | 86.6% | 27 ms | 40 ms | 0.11 | 0.42 | 0.89 | 85.5% |
| `e5-knn-router` | B) treinado | 73.0% | 60.4% | 0.0% | 88.9% | 26 ms | 35 ms | 0.10 | – | 0.71 | 82.4% |

\* concordância da decisão entre a fala original e a mesma fala sem acentos/pontuação/maiúsculas.

## Acurácia por fatia (tags)

| backend | clear | hard | ambiguous | short | long | asr | no_wake | mentions_wake | near_wake | background | to_human | english |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `julia-1` | 42.9% | 14.3% | 36.4% | 0.0% | 44.4% | 38.5% | 22.2% | 0.0% | 0.0% | 0.0% | 0.0% | 60.0% |
| `julia-1-pt` | 33.0% | 10.7% | 27.3% | 15.8% | 44.4% | 15.4% | 22.2% | 16.7% | 0.0% | 20.0% | 0.0% | 40.0% |
| `decider-0.8b-schema` | 91.2% | 35.7% | 90.9% | 89.5% | 66.7% | 69.2% | 88.9% | 33.3% | 50.0% | 60.0% | 61.5% | 100.0% |
| `decider-0.8b-schema-pt` | 83.5% | 35.7% | 90.9% | 94.7% | 66.7% | 76.9% | 77.8% | 33.3% | 0.0% | 0.0% | 15.4% | 100.0% |
| `laya` | 42.9% | 35.7% | 54.5% | 26.3% | 66.7% | 30.8% | 33.3% | 16.7% | 50.0% | 60.0% | 30.8% | 40.0% |
| `jeff-0.8b` | 90.1% | 39.3% | 81.8% | 78.9% | 100.0% | 69.2% | 88.9% | 50.0% | 50.0% | 20.0% | 46.2% | 100.0% |
| `jeff-0.8b-pt` | 91.2% | 42.9% | 100.0% | 89.5% | 88.9% | 76.9% | 88.9% | 33.3% | 100.0% | 20.0% | 61.5% | 100.0% |
| `jeff-0.8b-gate` | 84.6% | 78.6% | 81.8% | 73.7% | 88.9% | 46.2% | 100.0% | 83.3% | 50.0% | 80.0% | 76.9% | 60.0% |
| `qwen3.5-0.8b-logprob` | 52.7% | 25.0% | 63.6% | 63.2% | 22.2% | 46.2% | 55.6% | 16.7% | 0.0% | 0.0% | 7.7% | 80.0% |
| `qwen3.5-0.8b-chat` | 45.1% | 14.3% | 45.5% | 21.1% | 44.4% | 38.5% | 22.2% | 0.0% | 0.0% | 0.0% | 0.0% | 60.0% |
| `qwen3.5-2b-chat` | 82.4% | 46.4% | 81.8% | 94.7% | 77.8% | 84.6% | 66.7% | 66.7% | 50.0% | 20.0% | 30.8% | 100.0% |
| `qwen3.5-4b-chat` | 93.4% | 60.7% | 81.8% | 94.7% | 88.9% | 100.0% | 66.7% | 66.7% | 100.0% | 80.0% | 46.2% | 100.0% |
| `nli-mdeberta` | 25.3% | 25.0% | 63.6% | 26.3% | 44.4% | 23.1% | 44.4% | 0.0% | 0.0% | 0.0% | 7.7% | 20.0% |
| `gliclass-edge` | 52.7% | 7.1% | 72.7% | 21.1% | 77.8% | 38.5% | 55.6% | 16.7% | 0.0% | 0.0% | 7.7% | 80.0% |
| `e5-zeroshot` | 26.4% | 35.7% | 45.5% | 21.1% | 22.2% | 30.8% | 44.4% | 83.3% | 100.0% | 20.0% | 30.8% | 20.0% |
| `tfidf-logreg` | 82.4% | 46.4% | 90.9% | 78.9% | 77.8% | 100.0% | 77.8% | 50.0% | 50.0% | 80.0% | 69.2% | 60.0% |
| `e5-logreg` | 93.4% | 78.6% | 90.9% | 84.2% | 55.6% | 76.9% | 100.0% | 16.7% | 100.0% | 80.0% | 100.0% | 100.0% |
| `e5-knn-router` | 82.4% | 25.0% | 90.9% | 78.9% | 66.7% | 76.9% | 77.8% | 0.0% | 0.0% | 40.0% | 30.8% | 100.0% |

N por fatia: clear=91, hard=28, ambiguous=11, short=19, long=9, asr=13, no_wake=9, mentions_wake=6, near_wake=2, background=5, to_human=13, english=5

## Acurácia por classe

| backend | complex | home_control | ignore | knowledge | media | timer_alarm |
|---|---|---|---|---|---|---|
| `julia-1` | 66.7% | 90.6% | 1.7% | 4.8% | 44.4% | 40.0% |
| `julia-1-pt` | 40.0% | 3.1% | 8.6% | 33.3% | 72.2% | 66.7% |
| `decider-0.8b-schema` | 73.3% | 84.4% | 65.5% | 100.0% | 94.4% | 73.3% |
| `decider-0.8b-schema-pt` | 66.7% | 96.9% | 46.6% | 100.0% | 94.4% | 93.3% |
| `laya` | 46.7% | 90.6% | 32.8% | 19.0% | 11.1% | 26.7% |
| `jeff-0.8b` | 93.3% | 90.6% | 58.6% | 95.2% | 94.4% | 80.0% |
| `jeff-0.8b-pt` | 93.3% | 93.8% | 65.5% | 90.5% | 100.0% | 80.0% |
| `jeff-0.8b-gate` | 86.7% | 81.2% | 84.5% | 61.9% | 83.3% | 73.3% |
| `qwen3.5-0.8b-logprob` | 53.3% | 93.8% | 20.7% | 57.1% | 38.9% | 46.7% |
| `qwen3.5-0.8b-chat` | 13.3% | 100.0% | 1.7% | 57.1% | 55.6% | 13.3% |
| `qwen3.5-2b-chat` | 86.7% | 100.0% | 44.8% | 100.0% | 94.4% | 93.3% |
| `qwen3.5-4b-chat` | 93.3% | 100.0% | 72.4% | 95.2% | 94.4% | 100.0% |
| `nli-mdeberta` | 6.7% | 71.9% | 10.3% | 0.0% | 50.0% | 33.3% |
| `gliclass-edge` | 46.7% | 40.6% | 10.3% | 81.0% | 66.7% | 100.0% |
| `e5-zeroshot` | 13.3% | 56.2% | 25.9% | 0.0% | 33.3% | 33.3% |
| `tfidf-logreg` | 80.0% | 87.5% | 72.4% | 57.1% | 88.9% | 93.3% |
| `e5-logreg` | 100.0% | 87.5% | 89.7% | 85.7% | 77.8% | 73.3% |
| `e5-knn-router` | 100.0% | 100.0% | 44.8% | 85.7% | 72.2% | 80.0% |

## Economia de LLM (rotas knowledge/complex)

| backend | chamadas ao LLM | evitadas vs. mandar tudo | necessárias | perdidas | desperdiçadas |
|---|---|---|---|---|---|
| `julia-1` | 39/159 | 75.5% | 36 | 21 | 22 |
| `julia-1-pt` | 29/159 | 81.8% | 36 | 21 | 13 |
| `decider-0.8b-schema` | 49/159 | 69.2% | 36 | 3 | 13 |
| `decider-0.8b-schema-pt` | 56/159 | 64.8% | 36 | 2 | 19 |
| `laya` | 13/159 | 91.8% | 36 | 26 | 2 |
| `jeff-0.8b` | 46/159 | 71.1% | 36 | 3 | 10 |
| `jeff-0.8b-pt` | 40/159 | 74.8% | 36 | 4 | 5 |
| `jeff-0.8b-gate` | 32/159 | 79.9% | 36 | 11 | 6 |
| `qwen3.5-0.8b-logprob` | 28/159 | 82.4% | 36 | 16 | 6 |
| `qwen3.5-0.8b-chat` | 15/159 | 90.6% | 36 | 23 | 2 |
| `qwen3.5-2b-chat` | 46/159 | 71.1% | 36 | 2 | 10 |
| `qwen3.5-4b-chat` | 46/159 | 71.1% | 36 | 2 | 8 |
| `nli-mdeberta` | 1/159 | 99.4% | 36 | 36 | 1 |
| `gliclass-edge` | 38/159 | 76.1% | 36 | 12 | 11 |
| `e5-zeroshot` | 13/159 | 91.8% | 36 | 35 | 11 |
| `tfidf-logreg` | 36/159 | 77.4% | 36 | 9 | 8 |
| `e5-logreg` | 44/159 | 72.3% | 36 | 1 | 8 |
| `e5-knn-router` | 49/159 | 69.2% | 36 | 1 | 11 |

## Limiar de confiança (política: abaixo do limiar → ignorar)

- `julia-1`: τ=0.00: acc 34.6%, FA 100.0%, perdidos 0.0% · τ=0.50: acc 37.1%, FA 92.5%, perdidos 4.0% · τ=0.70: acc 38.4%, FA 69.8%, perdidos 23.2% · τ=0.90: acc 43.4%, FA 41.5%, perdidos 46.5%
- `julia-1-pt`: τ=0.00: acc 26.4%, FA 92.5%, perdidos 17.2% · τ=0.50: acc 28.3%, FA 81.1%, perdidos 35.4% · τ=0.70: acc 35.8%, FA 50.9%, perdidos 55.6% · τ=0.90: acc 39.0%, FA 26.4%, perdidos 75.8%
- `decider-0.8b-schema`: τ=0.00: acc 78.6%, FA 37.7%, perdidos 6.1% · τ=0.50: acc 78.6%, FA 35.8%, perdidos 11.1% · τ=0.70: acc 77.4%, FA 18.9%, perdidos 25.3% · τ=0.90: acc 69.2%, FA 5.7%, perdidos 46.5%
- `decider-0.8b-schema-pt`: τ=0.00: acc 75.5%, FA 58.5%, perdidos 3.0% · τ=0.50: acc 76.7%, FA 50.9%, perdidos 5.1% · τ=0.70: acc 77.4%, FA 32.1%, perdidos 16.2% · τ=0.90: acc 74.8%, FA 7.5%, perdidos 36.4%
- `laya`: τ=0.00: acc 40.9%, FA 67.9%, perdidos 7.1% · τ=0.50: acc 42.1%, FA 41.5%, perdidos 51.5% · τ=0.70: acc 44.0%, FA 15.1%, perdidos 74.7% · τ=0.90: acc 42.1%, FA 1.9%, perdidos 90.9%
- `jeff-0.8b`: τ=0.00: acc 79.2%, FA 45.3%, perdidos 4.0% · τ=0.50: acc 79.9%, FA 24.5%, perdidos 16.2% · τ=0.70: acc 79.2%, FA 13.2%, perdidos 26.3% · τ=0.90: acc 69.2%, FA 9.4%, perdidos 44.4%
- `jeff-0.8b-pt`: τ=0.00: acc 82.4%, FA 37.7%, perdidos 2.0% · τ=0.50: acc 83.6%, FA 22.6%, perdidos 11.1% · τ=0.70: acc 79.9%, FA 17.0%, perdidos 23.2% · τ=0.90: acc 67.9%, FA 13.2%, perdidos 44.4%
- `jeff-0.8b-gate`: τ=0.00: acc 79.9%, FA 17.0%, perdidos 21.2% · τ=0.50: acc 76.7%, FA 5.7%, perdidos 33.3% · τ=0.70: acc 61.0%, FA 1.9%, perdidos 61.6% · τ=0.90: acc 41.5%, FA 0.0%, perdidos 93.9%
- `qwen3.5-0.8b-logprob`: τ=0.00: acc 47.8%, FA 83.0%, perdidos 4.0% · τ=0.50: acc 51.6%, FA 54.7%, perdidos 25.3% · τ=0.70: acc 49.7%, FA 11.3%, perdidos 74.7% · τ=0.90: acc 39.6%, FA 0.0%, perdidos 97.0%

## Custo e memória

| backend | modelo | CPU-s/decisão | núcleos ocupados | RSS servidor | carga |
|---|---|---|---|---|---|
| `julia-1` | SupersonicLabs/Julia-1 (GGUF Q8_0, llama.cpp) | 0.825 | 3.3 | 486 MB | 0.1 s |
| `julia-1-pt` | SupersonicLabs/Julia-1 (GGUF Q8_0, llama.cpp) | 0.765 | 3.9 | 499 MB | 0.1 s |
| `decider-0.8b-schema` | Mapika/decider-0.8b (PyTorch CPU, schema cache) | 2.154 | 3.9 | 3486 MB | 0.2 s |
| `decider-0.8b-schema-pt` | Mapika/decider-0.8b (PyTorch CPU, schema cache) | 2.153 | 3.9 | 3528 MB | 0.1 s |
| `laya` | convaiinnovations/laya (GGUF Q8_0, llama.cpp) | 4.316 | 3.9 | 529 MB | 0.1 s |
| `jeff-0.8b` | mstrasser/Jeff-Qwen3.5-0.8B@v1.2 (PyTorch fp32, CPU) | 7.317 | 2.4 | 3957 MB | 0.1 s |
| `jeff-0.8b-pt` | mstrasser/Jeff-Qwen3.5-0.8B@v1.2 (PyTorch fp32, CPU) | 7.496 | 2.4 | 3960 MB | 0.1 s |
| `jeff-0.8b-gate` | mstrasser/Jeff-Qwen3.5-0.8B@v1.2 (PyTorch fp32, CPU) + noul gate | 12.623 | 2.5 | 3850 MB | 0.1 s |
| `qwen3.5-0.8b-logprob` | Qwen/Qwen3.5-0.8B (GGUF Q8_0, llama.cpp) - sem especialização | 7.783 | 3.8 | 1013 MB | 0.3 s |
| `qwen3.5-0.8b-chat` | Qwen/Qwen3.5-0.8B (GGUF Q8_0) | 9.927 | 3.8 | 1033 MB | 0.1 s |
| `qwen3.5-2b-chat` | Qwen/Qwen3.5-2B (GGUF Q4_K_M) | 13.948 | 3.9 | 1577 MB | 0.1 s |
| `qwen3.5-4b-chat` | Qwen/Qwen3.5-4B (GGUF Q4_K_M) | 33.278 | 3.8 | 4364 MB | 0.2 s |
| `nli-mdeberta` | MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7 | 4.348 | 3.9 | +1032 (no processo do lab) MB | 5.2 s |
| `gliclass-edge` | knowledgator/gliclass-multilang-edge | 0.399 | 3.9 | +920 (no processo do lab) MB | 6.0 s |
| `e5-zeroshot` | intfloat/multilingual-e5-small | 0.100 | 3.9 | +3 (no processo do lab) MB | 0.0 s |
| `tfidf-logreg` | tfidf+logreg | 0.004 | 1.7 | +286 (no processo do lab) MB | 3.1 s |
| `e5-logreg` | intfloat/multilingual-e5-small | 0.107 | 3.7 | +611 (no processo do lab) MB | 10.2 s |
| `e5-knn-router` | intfloat/multilingual-e5-small | 0.101 | 3.8 | +1 (no processo do lab) MB | 0.3 s |

## Escalonamento de intenções (classes definidas na requisição; 60 falas)

| backend | cenário | opções | acurácia | falsa ativação | perdidos | escolheu distrator | p50 |
|---|---|---|---|---|---|---|---|
| `decider-0.8b-schema` | gate | 2 | 76.7% | 63.2% | 5.3% | 0.0% | 515 ms |
| `decider-0.8b-schema` | n6 | 6 | 80.0% | 26.3% | 10.5% | 0.0% | 527 ms |
| `decider-0.8b-schema` | n12 | 12 | 81.7% | 26.3% | 10.5% | 0.0% | 523 ms |
| `decider-0.8b-schema` | n20 | 20 | 81.7% | 26.3% | 10.5% | 0.0% | 517 ms |
| `decider-0.8b-schema` | n32 | 32 | 76.7% | 21.1% | 15.8% | 5.0% | 542 ms |
| `julia-1` | gate | 2 | 68.3% | 100.0% | 0.0% | 0.0% | 74 ms |
| `julia-1` | n6 | 6 | 38.3% | 100.0% | 0.0% | 0.0% | 168 ms |
| `julia-1` | n12 | 12 | 30.0% | 100.0% | 0.0% | 1.7% | 197 ms |
| `julia-1` | n20 | 20 | 31.7% | 100.0% | 0.0% | 18.3% | 261 ms |
| `julia-1` | n32 | 32 | 1.7% | 100.0% | 0.0% | 93.3% | 215 ms |
| `gliclass-edge` | gate | 2 | 73.3% | 84.2% | 0.0% | 0.0% | 54 ms |
| `gliclass-edge` | n6 | 6 | 51.7% | 94.7% | 0.0% | 0.0% | 91 ms |
| `gliclass-edge` | n12 | 12 | 33.3% | 94.7% | 0.0% | 58.3% | 107 ms |
| `gliclass-edge` | n20 | 20 | 30.0% | 100.0% | 0.0% | 66.7% | 141 ms |
| `gliclass-edge` | n32 | 32 | 15.0% | 100.0% | 0.0% | 68.3% | 180 ms |
| `e5-zeroshot` | gate | 2 | 73.3% | 84.2% | 0.0% | 0.0% | 27 ms |
| `e5-zeroshot` | n6 | 6 | 33.3% | 68.4% | 68.4% | 0.0% | 25 ms |
| `e5-zeroshot` | n12 | 12 | 11.7% | 89.5% | 42.1% | 55.0% | 21 ms |
| `e5-zeroshot` | n20 | 20 | 11.7% | 89.5% | 34.2% | 63.3% | 20 ms |
| `e5-zeroshot` | n32 | 32 | 11.7% | 89.5% | 28.9% | 68.3% | 24 ms |
| `nli-mdeberta` | gate | 2 | 68.3% | 100.0% | 0.0% | 0.0% | 317 ms |
| `nli-mdeberta` | n6 | 6 | 35.0% | 84.2% | 13.2% | 0.0% | 1008 ms |
| `nli-mdeberta` | n12 | 12 | 35.0% | 84.2% | 13.2% | 1.7% | 1950 ms |
| `nli-mdeberta` | n20 | 20 | 35.0% | 84.2% | 13.2% | 6.7% | 3282 ms |
| `nli-mdeberta` | n32 | 32 | 35.0% | 84.2% | 13.2% | 6.7% | 5110 ms |
| `jeff-0.8b` | gate | 2 | 60.0% | 10.5% | 57.9% | 0.0% | 1984 ms |
| `jeff-0.8b` | n6 | 6 | 76.7% | 36.8% | 7.9% | 0.0% | 2861 ms |
| `jeff-0.8b` | n12 | 12 | 71.7% | 52.6% | 7.9% | 8.3% | 3369 ms |
| `jeff-0.8b` | n20 | 20 | 70.0% | 57.9% | 7.9% | 13.3% | 4185 ms |
| `jeff-0.8b` | n32 | 32 | 63.3% | 68.4% | 7.9% | 18.3% | 5654 ms |

## Fase 2 — router na frente do LLM (ponta a ponta pela API)

| estratégia | falas | tempo total | só decisões | só LLM | chamadas LLM | necessárias | desperdiçadas | perdidas | falsa ativação |
|---|---|---|---|---|---|---|---|---|---|
| none (tudo -> LLM 2B) | 80 | 178 s | 0 s | 178 s | 80 | 18 | 62 | 0 | 100.0% |
| cascade-e5-decider τ=0.0 | 80 | 143 s | 9 s | 134 s | 20 | 18 | 2 | 0 | 3.7% |
| decider-0.8b-schema τ=0.0 | 80 | 138 s | 43 s | 95 s | 24 | 18 | 5 | 0 | 25.9% |
| qwen3.5-4b-chat τ=0.0 | 80 | 795 s | 681 s | 114 s | 23 | 18 | 5 | 1 | 25.9% |
