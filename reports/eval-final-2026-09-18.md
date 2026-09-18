# Relatório de avaliação — golden set (SPEC.md §10)

Gerado em: 2026-09-18T14:35:29.314884+00:00
Golden set: `v1`, manifest_sha256 `43ec5d2321f5f5d28ad270b8acd8fd7f1fa7db5d8160e316e14ae2036956e1aa`
Amostra: 500 alerta(s) (180 tipologia crítica, 110 tipologia suspeita não crítica, 210 normal).

## Versões gravadas

- `rules_version`: 1
- `mapping_version`: 1
- `features_version`: 1
- `prompt_version`: 1

## Latência (fluxo `INVESTIGAR`/`PROPOR_ARQUIVAMENTO` completo, golden set real)

- p50 = 2487 ms, p95 = 16875 ms

## Gates Go/No-Go (`SPEC.md` §10)

| Métrica | Fórmula | Gate | Status | Valor | Aprovado |
| :--- | :--- | :--- | :--- | :--- | :---: |
| Recall crítico | RNF-01 | = 100% | medida | 18.33% | ❌ |

  33/180 alertas críticos do golden terminaram COS/NEEDS_HUMAN (nunca ARQUIVAMENTO). Cache semântico não está implementado nesta PoC (nenhum módulo de cache em src/), então a rodada já é 'cache desligado' por construção, como o RNF-01 exige.
| Grounding | RNF-02 | bruto ≥ 99% e final 0 | não medida | - | — |

  Nenhum alerta da amostra propôs citação (ver --limit ou cobertura do mapping).
| Redução de falsos positivos | 1 − FP_pipeline / FP_baseline | ≥ 65% | medida | 82.86% | ✅ |

  FP_pipeline = 36/210 alertas normais do golden terminaram COS/NEEDS_HUMAN (deveriam ser ARQUIVAMENTO); FP_baseline = 100% (legado T0.8 encaminha todo alerta que gera, SPEC.md §10, fórmula literal — não é escolha nova desta tarefa).
| Velocidade | tempo_manual_min / (latência_média_min + baseline.tempo_revisao_min) | ≥ 3x | medida | 7.96x | ✅ |

  tempo_manual_min=120.0, tempo_revisao_min=15.0 (config/baseline.yaml, provisórios); latência_média_min do golden set real (500 alertas).
| Redução de tokens | SPEC.md §3.3: 1 − tokens_pipeline / tokens_baseline | > 70% | medida | 80.00% | ✅ |

  tokens_pipeline = soma real dos 100/500 alertas que chamaram o LLM (triagem evita chamada nos demais, `PROPOR_ARQUIVAMENTO`); tokens_baseline = média real por chamada × 500, o contrafactual '100% via agentes' do SPEC.md §3.3 sem rodar o golden set uma segunda vez com triagem desligada — decisão de menor custo (MEMORY.md), pois cache semântico não está implementado nesta PoC (já é 'cache desligado' em toda rodada) e a única variável restante é a triagem, cujo efeito é medido diretamente pela fração de alertas que evitou o LLM.
| Latência | RNF-03 | p95 < 20 s | medida | 16.87 s | ✅ |

  p95 do fluxo INVESTIGAR completo (grafo) sobre golden set real, 500 alertas (não amostra sintética).
| Prazo interno | SPEC.md §3.1 | 100% dentro | medida | 100.00% | ✅ |

  Proxy de cobertura: fração de dossiês com `prazo_interno`/`prazo_regulatorio_analise` (DT-11) calculados e em ordem cronológica com `selecao_em`. A métrica literal do SPEC §3.1 (chegada em DRAFT_READY dentro do prazo em relação ao tempo real decorrido) não se aplica a uma rodada em lote único executada em minutos/horas — mesma ressalva já registrada em `gates.py::_gate_prazo` (T1.13).
| Privacidade | RNF-05 | 0 ocorrências | medida | 0 ocorrência(s) | ✅ |

  Varredura de CPF/CNPJ sintético dos payloads golden efetivamente rodados sobre `audit_events` + `alert_records` desta execução (mesma técnica de `tests/privacy/test_canary.py`, T1.12). Prompt capturado do LiteLLM não repetido aqui (já coberto pelo canário unitário); terceiro destino (logs) continua não medido, como no T1.12 (sem infraestrutura de log formada).
| Integridade da auditoria | API-08 após a execução | valid = true | medida | True | ✅ |

  Cadeia recalculada sobre o banco de auditoria da amostra desta execução.

**Go:** todos os gates atendidos. **No-Go:** recall, grounding final, privacidade ou integridade falhando — sem exceção (`SPEC.md` §10).

## Contexto de fechamento

- Resultado: **No-Go** (recall crítico 18,33%; grounding não medido).
- Fonte imutável: `reports/eval-golden-2026-09-18.json`, rodada única de 500 alertas iniciada em
  2026-09-18T14:35:29Z; este arquivo preserva os mesmos valores.
- Modelo principal: `ollama_chat/qwen2.5:1.5b`; `temperature=0`, `seed=42`, `num_ctx=2048`,
  `num_predict=60`, `num_thread=8` (`config/litellm.yaml`).
- Hardware de referência: Intel Core i7-1255U, 10 núcleos/12 threads, 15,7 GB RAM, CPU-only
  (`reports/benchmark-ollama-2026-09-15-v2.md`). Python 3.13.15.
- Portabilidade RNF-10: alias `investigacao_alt` (`ollama_chat/llama3.2:3b`) exercitado via LiteLLM em
  12,35 s, conforme `MEMORY.md`; nenhuma troca de código ou provedor cloud.
- Origem das medidas: runner `scripts/evaluate.py --golden data/golden/v1 --ollama`, manifesto v1 SHA-256
  `43ec5d2321f5f5d28ad270b8acd8fd7f1fa7db5d8160e316e14ae2036956e1aa`, auditoria e latências da própria
  execução; baseline operacional de `config/baseline.yaml`.
- Desvio controlado: a rodada ocorreu antes das correções finais de resiliência/cache/UI. O plano proíbe
  uma segunda leitura do golden para ajuste; por isso o release atual permanece **não validado/No-Go**, sem
  extrapolar a métrica antiga como aprovação do código posterior.
