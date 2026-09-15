# Benchmark Ollama — 2026-09-15-v2

Gate do `SPEC.md` (RNF-03, seção 5), ADR-010 e ADR-013. Prompts 100% sintéticos, sem dado pessoal.

## Ambiente
- CPU: 12th Gen Intel(R) Core(TM) i7-1255U (10 núcleos / 12 threads)
- RAM: 15.7 GB — GPU: Intel(R) Iris(R) Xe Graphics
- Energia: tomada — plano `Driver Booster Power Plan`
- SO: Windows-11-10.0.26200-SP0 — Python 3.13.15 — Ollama 0.34.0
- Parâmetros: temperature 0, seed 42, num_ctx 2048, saída por JSON Schema (DT-07), num_thread 8, 10 execuções medidas por nó (calibração/aquecimento descartados).

## Varredura de num_thread (3 execuções por valor, prefixo frio)

| num_thread | p50 (s) | Prompt tok/s | Geração tok/s |
| :--- | ---: | ---: | ---: |
| auto | 12.94 | 44.1 | 9.0 |
| 4 | 15.31 | 35.3 | 7.8 |
| 6 | 12.04 | 46.8 | 9.0 |
| 8 | 8.96 | 72.5 | 9.8 |
| 10 | 9.92 | 64.8 | 8.6 |
| 12 | 12.17 | 54.2 | 7.8 |

Escolhido pelo menor p50: **8**.

## Resultado por nó

| Nó | Modelo (digest) | Tokens in / out (média) | Prompt tok/s | Geração tok/s | p50 (s) | p95 (s) | Orçamento p95 (s) | Schema válido | Veredito |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| Investigação | `qwen2.5:1.5b` (65ec06548149) | 319 / 45 | 66.5 | 9.9 | 9.44 | 11.5 | 14.0 | 100% | **PASSA** |
| Investigação (prefixo estável) | `qwen2.5:1.5b` (65ec06548149) | 312 / 45 | 107.3 | 11.4 | 6.81 | 8.31 | 14.0 | 100% | informativo (PASSA) |

## Fluxo completo (estimado)
- p95 do nó LLM (gate): 11.5 s + etapas determinísticas orçadas 3.5 s (inclui Seleção de chunks determinística, ADR-013) = **15.0 s**
- Limite < 20 s: **PASSA** — com margem de 2.5 s: **PASSA**
- As etapas determinísticas entram pelo orçamento do SPEC; são medidas nos testes de avaliação (seção 10).

Dados brutos: `benchmark-ollama-2026-09-15-v2.json`.
