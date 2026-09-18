# Relatório de avaliação — M1 (T1.13)

Gerado em: 2026-09-18T15:30:08.910607+00:00
Amostra: 30 alerta(s) sintético(s), fluxo `INVESTIGAR` via API-01.

## Versões gravadas

- `rules_version`: 1
- `mapping_version`: 2
- `features_version`: 1
- `prompt_version`: 1
- `model`: ollama_chat/qwen2.5:1.5b
- `corpus_version`: eval-amostra-sintetica

## Latência (RNF-03, informativa — amostra sintética, não o golden set)

- Fluxo `INVESTIGAR` completo (grafo): p50 = 11214 ms, p95 = 18874 ms
- Só a chamada LLM (evento `MODEL_CALLED`): p50 = 8681 ms, p95 = 14166 ms
- Overhead do grafo sobre os 15.0 s estimados no ADR-013: +3.87 s

## Gates Go/No-Go (`SPEC.md` §10)

| Métrica | Fórmula | Gate | Status | Valor | Aprovado |
| :--- | :--- | :--- | :--- | :--- | :---: |
| Recall crítico | RNF-01 | = 100% | não medida | - | — |
| Grounding | RNF-02 | bruto ≥ 99% e final 0 | não medida | - | — |
| Redução de falsos positivos | 1 − FP_pipeline / FP_baseline | ≥ 65% | não medida | - | — |
| Velocidade | tempo_manual_min / (latência_média_min + baseline.tempo_revisao_min) | ≥ 3x | medida | 7.89x | ✅ |
| Redução de tokens | SPEC.md §3.3 | > 70% | não medida | - | — |
| Latência | RNF-03 | p95 < 20 s | medida | 18.87 s | ✅ |
| Prazo interno | SPEC.md §3.1 | 100% dentro | não medida | - | — |
| Privacidade | RNF-05 | 0 ocorrências | não medida | - | — |
| Integridade da auditoria | API-08 após a execução | valid = true | medida | True | ✅ |

Gate marcado "não medida" nunca é "aprovado" — cada linha traz a nota com o motivo e o marco que fecha a medição (`TASKS.md` §5).

## Investigação (Tarefa B, `tasks/final-tasks.md`) — p95 ainda acima dos 15 s do ADR-013

N=30 (vs. n=3 da T1.13, `reports/eval-2026-09-18.md`) confirma que **não era ruído de amostra pequena**: p95 do
fluxo completo continua acima do estimado no ADR-013 (18,87 s vs. 15,0 s, overhead +3,87 s) e o overhead do
grafo sobre a chamada isolada ao LLM (p95 fluxo 18,87 s − p95 só-LLM 14,17 s ≈ 4,7 s) é da mesma ordem de
grandeza do n=3 anterior (+4,69 s) — consistente, não uma anomalia pontual.

Este script (`eval/latency.py`) só mede dois pontos por alerta (total do `POST /alerts` e a duração do evento
`MODEL_CALLED`, via `audit_events`); não há instrumentação por nó do grafo (sanitização, triagem, extração de
features, montagem do dossiê, gravação de auditoria) para apontar qual nó concentra os ~4,7 s de overhead.
Adicionar essa instrumentação (novo tipo de evento de auditoria ou timer por nó em `graph/build.py`) é decisão
estrutural fora do escopo desta tarefa — **não implementada aqui, por instrução explícita de não otimizar/
instrumentar sem ADR**. Registrado como item aberto em `MEMORY.md`.
