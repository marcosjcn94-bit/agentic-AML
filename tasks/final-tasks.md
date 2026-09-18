# Tarefa: fechar os gates pendentes do projeto AML Guardian (PoC)

Você está no repositório `C:\Users\mjcn9\Desktop\PROJETOS\projeto_CI&T` — um PoC de triagem/investigação AML com LangGraph + Ollama local, documentado por `SPEC.md`, `SOUL.md`, `AGENTS.md`, `PLAN.md`, `TASKS.md`, com o estado de execução em `MEMORY.md`. Leia esses arquivos ANTES de qualquer código. Convenção do projeto: **MUST** = obrigatório; mudança estrutural vira ADR novo em `docs/ADR.md`.

Contexto: todos os marcos M0–M7 estão codificados e commitados. Restam **gaps registrados em `MEMORY.md`** (seção "M7 · gap conhecido" e "T1.13"). Sua missão é fechá-los, nesta ordem:

## Tarefa A — Modo `--golden` no `scripts/evaluate.py` (fecha 6 gates do SPEC §10)

Hoje o evaluate só mede amostra sintética (latência/velocidade/auditoria). Os outros 6 gates do `SPEC.md` §10 — **Recall crítico, Grounding, Redução de FP, Redução de tokens, Prazo interno, Privacidade final** — estão "não medida" porque exigem os 500 alertas de `data/golden/v1` pelo pipeline real.

O que fazer:
1. Estender `scripts/evaluate.py` com modo `--golden data/golden/v1` que carrega os 500 alertas do manifesto (`data/golden/v1/manifest.json`), roda cada um por `POST /alerts` (ou pelo grafo direto, reaproveitando `tests/e2e/test_e2e.py`) e agrega os 6 gates.
2. Redução de FP: comparar a recomendação final (`ARQUIVAR`/`COMUNICAR`) contra a decisão implícita do legado (gerador de alertas T0.8, `config/alert_rules.yaml`). Desenhar essa métrica exigirá escolha documentada — registrar em `MEMORY.md` quando fizer.
3. Recall crítico: 100% dos alertas das 6 tipologias críticas (`Layered_Fan_In`, `Layered_Fan_Out`, `Stacked_Bipartite`, `Deposit-Send`, `Structuring`, `Smurfing`) precisam terminar em `COMUNICAR` ou `NEEDS_HUMAN` — nunca `ARQUIVAR`.
4. Grounding: `%` de citações com `verified=true` do DT-10 sobre o conjunto de alertas que terminou `DRAFT_READY`.
5. Redução de tokens: tokens de prompt+completion do LLM por alerta, comparado contra baseline (registrar em `MEMORY.md` qual baseline usar — se não houver, medir e propor).
6. Prazo interno / Privacidade final: verificar que todo `DT-11` tem `prazo_interno`/`prazo_regulatorio_analise` calculados e que nenhum evento de auditoria carrega PII em claro (reuse do canário RNF-05).
7. **Não fabricar número**: se um gate não puder ser medido de ponta a ponta, deixar "não medida" com nota explicando por quê.
8. Rodada completa: ~500 alertas × Ollama local (`qwen2.5:1.5b` via LiteLLM). Estimado 1–2h. Rodar em background com log; pular tests `ollama`/`network` intermediários para não duplicar.
9. Gravar resultado em `reports/eval-golden-<data>.md` + atualizar gates no relatório.

## Tarefa B — Rodada de latência com N maior (fecha latência do ADR-013)

A rodada da T1.13 (`reports/eval-2026-09-18.md`) teve n=3 e p95=19,7s, acima dos 15s estimados. Rodar com `--sample-size 30` (ou 50) via Ollama real, amostra sintética, e gravar em `reports/eval-latency-<data>.md`. Se p95 continuar > 15s, investigar o overhead do grafo (instrumentar por nó) e reportar — **não** "otimizar" sem ADR.

## Tarefa C — Atualizar `MEMORY.md` e `TASKS.md`

Ao final:
- Marcar em `MEMORY.md` cada gate que passou a "medida" vs. "aprovado" com referência ao relatório.
- Em `tasks/M2-M7.md`, atualizar T7: se todos os 9 gates fecharem, marcar como concluído com a evidência.
- Commit atômico por tarefa, citando IDs (`RNF-03`, `RF-*`, `API-*`, `SPEC §10`).

## Regras duras (do `SOUL.md` / `AGENTS.md`)

- Não editar `SPEC.md`, `SOUL.md`, `AGENTS.md`, `PLAN.md`. Conflito → ADR novo em `docs/ADR.md`.
- Revisores: Revisor Python em toda mudança de código; Avaliador no fim de cada marco. Estão em `MEMORY.md` como agentes acionados a cada tarefa.
- Nenhum dado real/PII em testes. Dados sintéticos via fixtures existentes.
- Nenhum provedor cloud: só Ollama local (LiteLLM alias `investigacao` / `investigacao_alt`). Ver `config/litellm.yaml`.
- Não commitar `data/raw/`, `data/golden/*/payloads/`, `*.sqlite`, `logs/`.
- Push: **não fazer push**, só commit local. O autor faz push manualmente.