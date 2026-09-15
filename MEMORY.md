# MEMORY — Agentic AML & Regulatory Compliance Guardian (PoC)

Estado de execução das tarefas (`TASKS.md` §6), aprendizados, bugs persistentes e decisões tomadas no caminho (`SOUL.md`).

## Progresso

| Tarefa | Estado | Evidência |
| :--- | :--- | :--- |
| T0.1 — Projeto Python e guarda da stack | Concluída (`748d312`) | `pip install -e .[dev]` exit 0 · `pip check` ok · `.venv` `pytest -k stack`: 27 passed · `spacy.load('pt_core_news_lg')` ok |
| T0.2 — Contratos de ingestão e estado (DT-01 a DT-05) | Concluída | `pytest -k dt_ingestao`: 80 passed · Revisor Python: 1 médio resolvido, 2 baixos adiados |

## Decisões no caminho

- **2026-09-15 · T0.1 · Ask First aprovado:** dependências da stack do `SPEC.md` §6 com limites inferiores; complementares `uvicorn` e `pyyaml`.
- **2026-09-15 · T0.1:** `semgrep` fica no extra `security` (sem suporte nativo estável no Windows; rodar via WSL/Docker no M6), fora de `dev`.
- **2026-09-15 · T0.1:** `.venv` com Python 3.13 (3.14 é o padrão do sistema, mas há risco de wheels ausentes para spaCy/Presidio/ChromaDB).
- **2026-09-15 · T0.1:** `pt_core_news_lg` 3.8.0 declarado por URL direta no `pyproject.toml` (casado com `spacy>=3.8,<3.9`).
- **2026-09-15 · T0.2:** `amount_brl` > 0 com no máximo 2 casas decimais; `float`/`bool` recusados (evita imprecisão binária). Sem `max_digits` (SPEC não define teto).
- **2026-09-15 · T0.2:** DT-04 aceita em conta/nome/`cpf_cnpj` só token `^[A-Z]+_\d{2,}$`; amarrar prefixo por campo (`CPF_`, `CONTA_`, `NOME_`) fica para a T1.x do sanitizador, que define os tipos.
- **2026-09-15 · T0.2:** `PROPOR_ARQUIVAMENTO` é `TriageLevel`, não estado; DT-05 valida coerência estado ↔ nível pelo RF-10 (sem nível antes de `TRIAGED`; `INVESTIGAR` em `INVESTIGATING/RESEARCHING/REVIEWING`; `NEEDS_HUMAN` livre e exige `failure_reason`). Prazos do DT-05 anuláveis (calculados no nó Dossiê + Prazo).
- **2026-09-15 · T0.1:** pytest deseleciona `ollama` e `network` por padrão via `addopts`; `-m ollama`/`-m network` na linha de comando sobrepõe.

## Aprendizados

- `litellm` traz `openai` e `boto3` como dependências transitivas (instalados no `.venv`); a guarda (`tests/test_stack.py`) cobre apenas o declarado (incluindo `build-system.requires`) e os `import` em `src/`, conforme T0.1.
- Revisor Python da T0.1: nomes exatos `azure`/`google-cloud`, `import_module(name=...)` e `build-system.requires` eram brechas da guarda; cobertos por casos de teste.
