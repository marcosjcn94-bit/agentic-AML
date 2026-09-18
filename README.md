# AML Guardian

PoC local de PLD/FT que reduz falsos positivos sem delegar a decisão final à IA. O sistema sanitiza o alerta,
executa triagem determinística, usa um SLM local apenas para formular a hipótese, verifica citações normativas
por hash e entrega um dossiê auditável para decisão humana.

## Estado real

**No-Go para produção.** Na avaliação golden de 500 alertas, 7/9 gates foram medidos e aprovados, mas o
recall crítico foi 18,33% (gate: 100%) e o grounding não foi medido porque nenhuma citação foi proposta.
Também permanecem 11 advisories em dependências sem atualização compatível com o Presidio atual. Consulte
`reports/eval-final-2026-09-18.md` e `reports/security-final.md`.

O que a PoC demonstra: privacidade zero-trust, fluxo fail-closed, trilha append-only, API com papéis, UI
Streamlit, RAG normativo determinístico, testes de navegador e execução local sem provedor cloud.

## Arquitetura e guardrails

- FastAPI + LangGraph + SQLite para API, orquestração, checkpoint e auditoria.
- Presidio/spaCy e Vault somente em memória; PII não entra em LLM, RAG, cache ou logs.
- LiteLLM + Ollama (`qwen2.5:1.5b`); nenhum fallback para modelo maior.
- ChromaDB/FastEmbed + BM25/RRF; citação só entra no dossiê após SHA-256 válido.
- Apenas `compliance_officer` decide; a PoC não comunica ao COAF nem bloqueia transações.

Detalhes em `docs/ARCHITECTURE.md`, contratos em `SPEC.md` e decisões em `docs/ADR.md`.

## Requisitos

- Windows 10/11, PowerShell ou Git Bash;
- Python 3.11 a 3.13 (desenvolvimento validado em 3.13);
- Docker Desktop para Semgrep/ZAP;
- Ollama com `qwen2.5:1.5b` e `llama3.2:3b` para testes reais de modelo.

## Instalação

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m playwright install chromium
Copy-Item .env.example .env
ollama pull qwen2.5:1.5b
ollama pull llama3.2:3b
```

Os valores de `.env.example` são fictícios. Troque-os apenas no `.env`, que não é versionado.

## Execução

Em terminais separados:

```powershell
ollama serve
.\.venv\Scripts\python.exe -m uvicorn aml_guardian.api.app:create_app --factory --port 8000
.\.venv\Scripts\python.exe -m streamlit run src/aml_guardian/ui/app.py
```

Abra `http://localhost:8501`. A API expõe `/health`; estado `degraded` indica dependência local indisponível.
O roteiro reproduzível está em `docs/DEMO.md`.

## Validação

```powershell
.\.venv\Scripts\ruff.exe check src tests scripts
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\bandit.exe -q -lll -r src
.\.venv\Scripts\pip-audit.exe
```

O `pytest` padrão é offline quanto a Ollama e rede, mas inclui Chromium local. A avaliação golden real já
foi executada uma vez; não deve ser repetida para calibrar regras. Para smoke de infraestrutura:

```powershell
.\.venv\Scripts\python.exe scripts/evaluate.py --golden data/golden/v1 --limit 3 --ollama
```

## Estrutura

```text
config/                 regras e aliases versionados
data/mappings/          curadoria SAML-D → CC 4.001
src/aml_guardian/       API, grafo, agentes determinísticos, UI e persistência
tests/                  contratos, unidade, integração, privacidade e navegador
scripts/                avaliação, dados, benchmark e segurança
reports/                evidências reproduzíveis e resultado No-Go
```

## Limitações

- recall crítico abaixo do gate e grounding sem amostra na rodada final;
- dependências com advisories residuais documentados;
- Vault em memória: reiniciar a API torna reidentificação anterior indisponível;
- PoC local, sem alta disponibilidade, integração COAF ou uso de dados reais.

O dataset SAML-D possui licença de uso não comercial; confirme os termos da origem antes de redistribuir ou
usar fora de estudo, portfólio e pesquisa.
