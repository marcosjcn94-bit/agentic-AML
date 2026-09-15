# MEMORY — Agentic AML & Regulatory Compliance Guardian (PoC)

Estado de execução das tarefas (`TASKS.md` §6), aprendizados, bugs persistentes e decisões tomadas no caminho (`SOUL.md`).

## Progresso

| Tarefa | Estado | Evidência |
| :--- | :--- | :--- |
| T0.1 — Projeto Python e guarda da stack | Pronta (commit pendente de aceite) | `pip install -e .[dev]` exit 0 · `pip check` ok · `.venv` `pytest -k stack`: 27 passed · `spacy.load('pt_core_news_lg')` ok |

## Decisões no caminho

- **2026-09-15 · T0.1 · Ask First aprovado:** dependências da stack do `SPEC.md` §6 com limites inferiores; complementares `uvicorn` e `pyyaml`.
- **2026-09-15 · T0.1:** `semgrep` fica no extra `security` (sem suporte nativo estável no Windows; rodar via WSL/Docker no M6), fora de `dev`.
- **2026-09-15 · T0.1:** `.venv` com Python 3.13 (3.14 é o padrão do sistema, mas há risco de wheels ausentes para spaCy/Presidio/ChromaDB).
- **2026-09-15 · T0.1:** `pt_core_news_lg` 3.8.0 declarado por URL direta no `pyproject.toml` (casado com `spacy>=3.8,<3.9`).
- **2026-09-15 · T0.1:** pytest deseleciona `ollama` e `network` por padrão via `addopts`; `-m ollama`/`-m network` na linha de comando sobrepõe.

## Aprendizados

- `litellm` traz `openai` e `boto3` como dependências transitivas (instalados no `.venv`); a guarda (`tests/test_stack.py`) cobre apenas o declarado (incluindo `build-system.requires`) e os `import` em `src/`, conforme T0.1.
- Revisor Python da T0.1: nomes exatos `azure`/`google-cloud`, `import_module(name=...)` e `build-system.requires` eram brechas da guarda; cobertos por casos de teste.
