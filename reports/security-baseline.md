# Baseline de segurança — Task 1

Data da execução: 2026-09-18.

## Comandos e resultados

| Comando | Resultado |
| --- | --- |
| `.venv/Scripts/python.exe -m pip check` | OK — `No broken requirements found.` |
| `.venv/Scripts/bandit.exe -q -r src` | OK sem High; 2 Medium e 11 Low existentes |
| `.venv/Scripts/ruff.exe check src tests` | OK |
| `.venv/Scripts/python.exe -m pytest tests/dossier tests/test_stack.py -q` | OK — 36 passed |
| `.venv/Scripts/pip-audit.exe` | 11 vulnerabilidades conhecidas restantes em `chromadb` e `cryptography` após a atualização |

## Disposição

- `B701` do Jinja foi eliminado habilitando autoescape no renderer e cobrindo HTML ativo com teste.
- `langchain-text-splitters` foi atualizado para `1.1.2`, versão com correção disponível; o aviso correspondente deixou de aparecer.
- `cryptography` foi testado em `50.0.1`, mas essa versão quebra a restrição de `presidio-anonymizer 2.2.364` (`<49`). O ambiente foi restaurado para `48.0.1` e o projeto registra explicitamente `>=48.0.1,<49`; a correção completa depende de uma versão compatível do Presidio.
- Os avisos restantes de `cryptography` e ChromaDB permanecem risco residual documentado. Não foram mascarados nem tratados como aprovados.

O estado de segurança desta etapa é parcial: não há High no Bandit, mas o gate de dependências não pode ser declarado aprovado enquanto houver advisories abertas sem compatibilidade de dependências.
