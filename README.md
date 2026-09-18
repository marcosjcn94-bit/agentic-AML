# AML Guardian

PoC de triagem AML/PLD com sanitização antes do grafo, investigação local via Ollama,
recuperação normativa com citações verificadas e decisão humana auditável.

## Estado

O projeto permanece **No-Go** para produção: o baseline golden anterior registrou recall
crítico de 18,33%. A implementação não altera essa métrica sem uma nova avaliação autorizada.
Também há advisories residuais documentados em `reports/security-baseline.md`.

## Execução local

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"
copy .env.example .env
.\.venv\Scripts\python -m uvicorn aml_guardian.api.app:create_app --factory
streamlit run src/aml_guardian/ui/app.py
```

O modelo local é configurado em `config/litellm.yaml`; nenhum dado deve sair da máquina.
Consulte `docs/DEMO.md`, `docs/ARCHITECTURE.md` e `SPEC.md` para os contratos completos.

## Testes e segurança

```powershell
.\.venv\Scripts\ruff check src tests scripts
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\bandit -q -r src
.\.venv\Scripts\pip-audit
```

A licença e os limites não comerciais do SAML-D devem ser respeitados.
