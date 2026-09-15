# TASKS — Agentic AML & Regulatory Compliance Guardian (PoC)

| Campo | Valor |
| :--- | :--- |
| Versão | 1.0.0 |
| Status | Aprovado |
| Origem | `INTENT.md` · `SPEC.md` 1.1.0 · `SOUL.md` 1.0.0 · `AGENTS.md` 1.0.0 · `PLAN.md` 1.0.0 (todos aprovados em 2026-09-15) |
| Decisões vinculadas | `docs/ADR.md` — ADR-001 a ADR-013 |
| Escopo desta versão | M0 e M1 (M2–M7 detalhados após o gate do M1) |
| Evidência reutilizada | `scripts/bench_ollama.py` · `reports/benchmark-ollama-2026-09-15-v2.md` |
| Gate | Aprovado por: marcosjcn94@gmail.com — Data: 2026-09-15 |

Convenção: **MUST** = obrigatório; **MUST NOT** = proibido (igual ao `SPEC.md`).
Este documento **não cria** requisito, meta, norma, limiar ou número de artigo: decompõe os marcos do `PLAN.md` em fatias verticais executáveis.
Toda tarefa aponta para os IDs de origem (`RF`, `RNF`, `API`, `MCP`, `DT`) e para o seu teste focado. Onde um valor ainda não foi aprovado, a tarefa
registra **Ask First** em vez de fixar o número.

---

## 1. Como executar uma tarefa

- **Uma tarefa = uma fatia vertical = uma sessão de implementação** (`AGENTS.md` §6).
- **Ciclo:** ler a tarefa e os IDs citados → teste focado vermelho → código mínimo → teste focado verde (`pytest -k <filtro>`) → revisores → `MEMORY.md`.
- **Revisores (`AGENTS.md` §6):** Revisor Python em toda tarefa com código; Guardião de privacidade e segurança quando a tarefa toca sanitizador,
  logging, prompt, cache, Vault ou servidor MCP; Avaliador no fim do marco (a partir do M1).
- **Canário RNF-05:** obrigatório quando a tarefa toca sanitizador, logging, prompt, cache ou servidor MCP (`SOUL.md` §4). Antes da T1.12 existir,
  a tarefa inclui um teste local equivalente sobre os destinos que ela cria.
- **Dados de teste:** sintéticos e gerados em tempo de execução; documento de identificação só aparece versionado como token (`CPF_01`).
- **Ask First:** a tarefa para e pede aceite do autor antes do código afetado. Decisão estrutural vira ADR novo antes do código.
- **Commit, push e branch:** só com aceite do autor, citando os IDs tocados.

Formato de cada tarefa:

| Campo | Conteúdo |
| :--- | :--- |
| IDs | Requisitos e contratos tocados |
| Depende de | Tarefas que precisam estar prontas |
| Entregas | Arquivos criados ou alterados |
| Teste focado | Arquivo e filtro `pytest -k`, com os casos obrigatórios |
| Ask First | Decisões que exigem aceite antes do código |
| Revisores | `AGENTS.md` §6 |
| Pronto quando | Critério objetivo de término |

---

## 2. Layout do repositório

Layout proposto uma vez; as tarefas referenciam os caminhos abaixo.

```text
pyproject.toml
config/                      triage_rules.yaml · litellm.yaml · baseline.yaml · feriados.yaml
data/
  raw/                       SAML-D baixado pelo autor (não versionado)
  mappings/                  saml_d_to_cc4001.yaml
  golden/v1/                 manifesto congelado por hash
  corpus/                    textos normativos baixados + metadados
src/aml_guardian/
  contracts/                 DT-01..DT-16, InvestigationState, registro de schema_version
  config/                    loaders tipados dos YAML
  sourcedata/                loader SAML-D, camada brasileira, gerador de alertas, golden set
  persistence/               app.sqlite (WAL), repositório DT-05, checkpoint
  audit/                     DT-12, hash-chain, triggers
  sanitizer/                 regex + DV, Presidio, tokens, Vault, KeyProvider
  mcp_servers/               MCP-01..MCP-04 (stdio) + cliente comum
  triage/                    detectores e TriageDecision
  features/                  pré-passo DT-16
  investigation/             contrato v1, montador de prompt, Router LiteLLM, pós-processamento
  norms/                     ingestão, chunking, ChromaDB
  retrieval/                 Recuperação e Seleção
  review/                    Revisor
  dossier/                   templates Jinja2
  deadlines/                 prazos
  graph/                     LangGraph, nós, arestas, envelopes
  api/                       FastAPI
scripts/                     bench_ollama.py (inalterado) · evaluate.py
tests/                       espelha src/aml_guardian/
```

- Marcadores pytest: `ollama` (exige modelo local carregado) e `network` (exige download). Testes sem marcador rodam offline.
- `.gitignore` já exclui `*.sqlite`, `chroma/` e `logs/`; a T0.1 acrescenta `data/raw/` e os payloads regenerados do golden set.

---

## 3. Marcos detalhados

Cada marco fica num arquivo próprio para manter os arquivos abaixo de 300 linhas (`CLAUDE.md`, Code Style & Architecture).

| Marco | Objetivo (`PLAN.md` §2) | Tarefas | Arquivo |
| :--- | :--- | :--- | :--- |
| M0 | Fundação, contratos e dados sintéticos | T0.1 a T0.9 + gate de saída | [`tasks/M0.md`](tasks/M0.md) |
| M1 | Esqueleto ponta a ponta (pré-condição: gate do M0) | T1.1 a T1.13 + gate de saída | [`tasks/M1.md`](tasks/M1.md) |

---

## 4. Rastreabilidade das entregas do `PLAN.md`

| Entrega (`PLAN.md` §3) | Tarefa |
| :--- | :--- |
| **M0** — Projeto Python 3.11+ com a stack obrigatória, sem dependência proibida | T0.1 |
| M0 — Schemas Pydantic v2 de DT-01 a DT-16, DT-14 por `schema_version`, `InvestigationState` | T0.2, T0.3, T0.4 |
| M0 — `config/` versionado (`triage_rules`, `litellm`, `baseline`, `feriados`) | T0.5 |
| M0 — `data/mappings/saml_d_to_cc4001.yaml` com `mapping_version` | T0.6 |
| M0 — Loader do SAML-D com falha explícita | T0.6 |
| M0 — Camada brasileira → `data/core_sintetico.sqlite` | T0.7 |
| M0 — Gerador de alertas legado com regra dos 45 dias e taxa de FP | T0.8 |
| M0 — Conjunto de desenvolvimento disjunto e `data/golden/v1` congelado | T0.9 |
| **M1** — Grafo LangGraph, envelopes e checkpoint SQLite | T1.10 |
| M1 — Sanitizador funcional e Vault | T1.2 |
| M1 — MCP-01 a MCP-04 via stdio com regras comuns | T1.3, T1.7 |
| M1 — Triagem inicial com os quatro detectores críticos | T1.4 |
| M1 — DT-16 `features_version = 1` | T1.5 |
| M1 — Investigação com contrato v1, teto de 300 tokens e pós-processamento RF-05 | T1.6 |
| M1 — LiteLLM Router com alias e parâmetros ADR-010/ADR-013 | T0.5, T1.6 |
| M1 — Corpus inicial com chunking por dispositivo na coleção `norms` | T1.7 |
| M1 — Recuperação, Seleção, Revisor e Dossiê Jinja2 | T1.8, T1.9 |
| M1 — `prazo_interno` e `prazo_regulatorio_analise` | T1.9 |
| M1 — Auditoria append-only com hash-chain e triggers | T1.1 |
| M1 — API-01, API-03, API-09 com Bearer por papel | T1.11 |
| M1 — `scripts/evaluate.py` inicial | T1.13 |

---

## 5. Marcos seguintes

Detalhados após o gate do M1 em `tasks/M<n>.md`, com o mesmo formato, e incluídos na §3 em nova versão deste documento.

| Marco | Objetivo (`PLAN.md` §2) | Depende de |
| :--- | :--- | :--- |
| M2 | Privacidade Zero-Trust | M1 |
| M3 | Triagem determinística e recall crítico | M1 |
| M4 | RAG normativo, Revisor e cache | M2, M3 |
| M5 | Resiliência, auditoria e prazos | M4 |
| M6 | Fluxo humano, UI e segurança | M5 |
| M7 | Avaliação Go/No-Go | M6 |

---

## 6. Governança deste documento

- **Precedência:** `SOUL.md` §5. Este documento não pode afrouxar nenhum limite do `SPEC.md`, `SOUL.md`, `AGENTS.md` ou `PLAN.md`; em conflito, vale a regra mais restritiva e o conflito é registrado em ADR.
- **Abrangência:** esta governança vale para o índice e para todos os arquivos `tasks/M<n>.md`, que compartilham a versão deste documento e ficam abaixo de 300 linhas (`CLAUDE.md`).
- **Mudança:** alterar escopo, dependência ou teste focado de tarefa incrementa a versão deste documento. Tarefa que exige mudar contrato, regra, limiar, prompt, modelo ou dependência para antes do código (Ask First).
- **Progresso:** o estado de execução de cada tarefa fica no `MEMORY.md` e no histórico de commits, não neste documento.
- **Revisão:** reler este documento sempre que `SPEC.md`, `SOUL.md`, `AGENTS.md` ou `PLAN.md` mudarem de versão.

## Gate
Status: aprovado pelo autor em 2026-09-15. A execução começa pela T0.1; M2–M7 entram em nova versão após o gate do M1.
