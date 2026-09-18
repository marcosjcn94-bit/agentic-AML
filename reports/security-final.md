# Security scan

| Ferramenta | Disponível |
|---|---|
| `bandit` | sim |
| `pip-audit` | sim |
| `semgrep` | sim |
| `zap-baseline.py` (local/Docker) | sim |

Ferramentas ausentes não são consideradas aprovadas.

## Evidências

- ZAP baseline via Docker: 66 verificações aprovadas, 0 falhas e 1 alerta
  informativo de conteúdo cacheável em URLs 404 (`robots.txt` e
  `sitemap.xml`). Detalhes: `reports/zap-baseline-2026-09-18.md`.
- Bandit: 0 achados High.
- `pip check`: dependências consistentes.
- `pip-audit`: 11 vulnerabilidades conhecidas em `chromadb 1.5.9` e
  `cryptography 48.0.1`; permanecem risco residual porque não há versão de
  correção compatível com a restrição atual do Presidio.
