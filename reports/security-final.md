# Security scan

| Ferramenta | Disponível |
|---|---|
| `bandit` | sim |
| `pip-audit` | sim |
| `semgrep` | sim |
| `zap-baseline.py` | não |

Ferramentas ausentes não são consideradas aprovadas.
Indisponíveis: zap-baseline.py
## Resultados executados

- Bandit com severidade High: aprovado, 0 achados High.
- `pip check`: aprovado, dependências consistentes.
- `pip-audit`: 11 advisories em `chromadb 1.5.9` e `cryptography 48.0.1`.
- Correções disponíveis para `cryptography` exigem `49.0.0` ou `50.0.0`, incompatíveis com o limite atual de `presidio-anonymizer` (`<49`).
- O gate de segurança permanece pendente por ZAP ausente e advisories sem combinação compatível validada.
