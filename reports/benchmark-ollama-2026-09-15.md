# Benchmark Ollama — 2026-09-15

Gate do `SPEC.md` (RNF-03, seção 5) e ADR-010. Prompts 100% sintéticos, sem dado pessoal.

## Ambiente
- CPU: 12th Gen Intel(R) Core(TM) i7-1255U (10 núcleos / 12 threads)
- RAM: 15.7 GB — GPU: Intel(R) Iris(R) Xe Graphics
- SO: Windows-11-10.0.26200-SP0 — Python 3.13.15 — Ollama 0.34.0
- Parâmetros: temperature 0, seed 42, num_ctx 2048, format json, 10 execuções medidas por nó (calibração/aquecimento descartados), nonce no início do prompt para evitar cache de prompt.

## Resultado por nó

| Nó | Modelo (digest) | Tokens in / out (média) | Prompt tok/s | Geração tok/s | p50 (s) | p95 (s) | Orçamento p95 (s) | JSON válido | Veredito |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :--- |
| Investigação | `qwen2.5:3b` (357c53fb659c) | 822 / 150 | 24.9 | 6.9 | 54.11 | 61.04 | 12.0 | 0% | **NÃO PASSA** |
| Seleção de chunks | `qwen2.5:1.5b` (65ec06548149) | 790 / 60 | 44.6 | 10.0 | 24.01 | 28.16 | 3.0 | 0% | **NÃO PASSA** |

## Fluxo completo (estimado)
- Soma p95 dos nós LLM: 89.2 s + etapas determinísticas orçadas 3.0 s = **92.2 s**
- Limite 20 s: **NÃO PASSA** — com margem de 2.0 s: **NÃO PASSA**
- Somar p95 de nós é conservador (os piores casos raramente coincidem).

Dados brutos: `benchmark-ollama-2026-09-15.json`.
