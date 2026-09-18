# Conclusão do AML Guardian — Plano de Implementação para Codex

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** concluir a PoC conforme `SPEC.md`, eliminar os gaps técnicos registrados, obter evidência reproduzível e entregar um projeto demonstrável para portfólio, sem ocultar eventual resultado No-Go.

**Architecture:** preservar a arquitetura existente: FastAPI no perímetro, sanitização antes do LangGraph, apenas Investigação usando LLM via LiteLLM/Ollama, demais nós determinísticos, dados por MCP, checkpoints e auditoria em SQLite. O trabalho será dividido em tarefas pequenas e revisáveis; contratos e segurança vêm antes da UI e da avaliação final.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, LangGraph, LiteLLM, Ollama, MCP, SQLite, ChromaDB/FastEmbed, Streamlit, pytest, Playwright, Ruff, Bandit, pip-audit, Semgrep e OWASP ZAP.

**Spec:** `SPEC.md` 1.1.0; documentos vinculantes `SOUL.md`, `AGENTS.md`, `PLAN.md`, `TASKS.md`, `MEMORY.md` e `docs/ADR.md`.

## Global Constraints

- Repositório: `C:\Users\mjcn9\Desktop\PROJETOS\projeto_CI&T`.
- Antes de editar, ler nesta ordem: `SOUL.md`, `SPEC.md`, `AGENTS.md`, `PLAN.md`, `TASKS.md`, `MEMORY.md`, `CLAUDE.md` e este plano.
- `SPEC.md`, `SOUL.md`, `AGENTS.md` e `PLAN.md` são imutáveis durante a execução.
- Mudança estrutural exige ADR novo antes do código; o próximo número é ADR-019.
- Não ajustar regra, limiar, prompt ou mapeamento usando exemplos individuais do golden set. Calibração usa somente o conjunto de desenvolvimento disjunto.
- Não fabricar métricas. Gate não exercitado permanece `não medida`; gate exercitado e reprovado permanece reprovado.
- Apenas Ollama local; nenhuma API cloud e nenhum SDK proprietário direto.
- Nenhum PII real; fixtures e exemplos usam dados sintéticos gerados em runtime ou tokens.
- Não versionar `.env`, credenciais, `*.sqlite`, `data/raw/`, payloads do golden, logs ou coleções ChromaDB.
- Arquivo novo/refatorado deve ter menos de 300 linhas; separar por responsabilidade.
- TDD por tarefa: teste vermelho, implementação mínima, teste verde, Ruff e revisão do diff.
- Codex não executa `git add`, `git commit` ou `git push`. O orquestrador revisa e cria o commit após validar cada tarefa.
- Não rodar a avaliação golden completa durante desenvolvimento. Rodar apenas uma vez ao final de todas as correções aprovadas; smoke tests usam `--limit` e não servem para calibrar regras.
- Comandos executados em Git Bash; caminhos de programas nativos usam `C:/...`.

## Estado auditado em 2026-09-18

- Git limpo na branch `chore/review-token-economy`.
- Ruff: `All checks passed!`.
- Testes offline: 715 aprovados e 2 desmarcados, executados em quatro lotes (`436 + 54 + 110 + 115`).
- `pip check`: sem requisitos quebrados.
- Golden real: Recall crítico 18,33% (33/180), portanto **No-Go**; Grounding não medido porque nenhuma citação foi proposta.
- Bandit: 1 High, 2 Medium e 11 Low; o High é `B701` em `dossier/renderer.py`.
- pip-audit: 13 vulnerabilidades conhecidas em `chromadb`, `cryptography` e `langchain-text-splitters`.
- Não existem README, UI Streamlit, workflow CI ou Dockerfile.
- `src/aml_guardian/retrieval/query.py` declara explicitamente “sem cache”; RF-04 não foi implementado.
- APIs 02, 05, 07 e 08 não existem; API-04 e API-06 usam rotas/semântica diferentes do contrato.
- API-01 retorna 409 para qualquer repetição, mas RF-01 exige 200 para payload idêntico e 409 apenas para conflito.
- A decisão do officer pula `SUBMITTED`, permitindo `DRAFT_READY → APPROVED`, contrário a RF-10/RF-12.
- Reidentificação atual não grava `PII_REVEALED`, não envia `Cache-Control: no-store`, não implementa 410 e não segue a rota API-04.
- Budget de 2.000 tokens/40 s, timeout por nó, retries com backoff e retomada após processo morto não estão fechados.
- Logs estruturados RNF-08, Semgrep e ZAP não têm evidência final.
- Apenas `Structuring` possui `article_ref` e `applicability` curados; isso impede medir grounding para as demais tipologias.

---

### Task 1: Registrar plano de remediação e corrigir o baseline de segurança

**Files:**
- Modify: `docs/ADR.md`
- Modify: `pyproject.toml`
- Modify: `src/aml_guardian/dossier/renderer.py`
- Create: `reports/security-baseline.md`
- Test: `tests/dossier/test_dossier.py`
- Test: `tests/test_stack.py`

**Interfaces:**
- Produces: ADR-019 descrevendo a remediação do No-Go sem uso do golden para calibração.
- Produces: dependências instaláveis sem vulnerabilidade corrigível de severidade alta/crítica.

- [ ] **Step 1: adicionar ADR-019 antes de mudar regras ou mapeamento**

Registrar: causa observada (detectores não cobrem as seis tipologias críticas e mapeamento normativo incompleto), restrição de calibrar somente no desenvolvimento, plano de ampliar detectores determinísticos e curadoria normativa, e regra de uma única nova rodada golden ao final.

- [ ] **Step 2: criar testes de renderização que permitam autoescape seguro**

Adicionar casos que confirmem que conteúdo potencialmente interpretável como HTML é escapado e que o snapshot textual continua contendo os campos regulatórios obrigatórios.

Run:

```bash
.venv/Scripts/python.exe -m pytest tests/dossier/test_dossier.py -q
```

Expected before implementation: pelo menos um novo teste falha.

- [ ] **Step 3: eliminar o High do Bandit**

Configurar Jinja com `select_autoescape` ou escape explícito compatível com o formato renderizado. Não silenciar `B701` sem alterar o comportamento inseguro. Se a saída oficial permanecer Markdown, garantir por teste que valores externos não produzam HTML ativo.

- [ ] **Step 4: atualizar dependências com correção disponível**

Elevar `cryptography` para versão que corrija os avisos atuais. Resolver `langchain-text-splitters` sem quebrar a integração opcional de Langfuse; se o conflito vier apenas da observabilidade opcional, preferir remover a dependência indireta não necessária ou atualizar o conjunto Langfuse/LangChain de forma coerente. Para avisos de ChromaDB sem versão corrigida, documentar ID, impacto, exposição da PoC e mitigação no relatório; não alegar correção inexistente.

- [ ] **Step 5: validar instalação e segurança**

Run:

```bash
.venv/Scripts/python.exe -m pip check
.venv/Scripts/bandit.exe -q -r src
.venv/Scripts/pip-audit.exe
.venv/Scripts/ruff.exe check src tests
.venv/Scripts/python.exe -m pytest tests/dossier tests/test_stack.py -q
```

Acceptance:
- Bandit sem High/Critical abertos.
- pip-audit sem vulnerabilidade alta/crítica com correção disponível; exceções sem fix devem estar identificadas em `reports/security-baseline.md`.
- Testes focados e Ruff verdes.

**Orchestrator commit:** `fix(security): close static and dependency findings [RNF-07]`

---

### Task 2: Completar persistência e idempotência da API-01

**Files:**
- Modify: `src/aml_guardian/persistence/db.py`
- Modify: `src/aml_guardian/persistence/repository.py`
- Modify: `src/aml_guardian/api/routes.py`
- Modify: `tests/api/test_api.py`

**Interfaces:**
- Produces: `save_ingestion_hash(alert_id: UUID, payload_sha256: str, db_path: Path | None) -> None`.
- Produces: `get_ingestion_hash(alert_id: UUID, db_path: Path | None) -> str | None`.
- Hash: SHA-256 do JSON canônico de `Alert.model_dump(mode="json")`; nunca persistir payload bruto.

- [ ] **Step 1: escrever testes RED para RF-01**

Casos obrigatórios:
- primeiro payload válido retorna 202;
- mesma `alert_id` e mesmo payload retorna 200 com estado atual, sem executar o grafo novamente e sem duplicar auditoria;
- mesma `alert_id` com qualquer campo diferente retorna 409;
- payload inválido retorna 422 e não cria registro nem hash.

- [ ] **Step 2: criar armazenamento mínimo do hash de ingestão**

Criar tabela `alert_ingestions(alert_id TEXT PRIMARY KEY, payload_sha256 TEXT NOT NULL)` em `init_db`; não alterar DT-05.

- [ ] **Step 3: implementar idempotência antes da sanitização**

Fluxo de `post_alert`:
1. calcular hash canônico;
2. se não existe, processar e persistir hash junto ao primeiro registro;
3. se hash igual, devolver 200 com estado atual;
4. se hash diferente, devolver 409.

Garantir consistência transacional suficiente para chamadas sequenciais da PoC e não incluir PII no hash reversível/log.

- [ ] **Step 4: validar**

```bash
.venv/Scripts/python.exe -m pytest tests/api/test_api.py -k "PostAlerts or idempot" -q
.venv/Scripts/ruff.exe check src/aml_guardian/api src/aml_guardian/persistence tests/api
```

Acceptance: RF-01 demonstra 200/409/422 e zero reprocessamento da repetição idêntica.

**Orchestrator commit:** `fix(api): enforce alert ingestion idempotency [RF-01 API-01]`

---

### Task 3: Implementar APIs 02–08 e a máquina humana correta

**Files:**
- Create: `src/aml_guardian/api/alerts.py`
- Create: `src/aml_guardian/api/dossiers.py`
- Create: `src/aml_guardian/api/audit.py`
- Modify: `src/aml_guardian/api/routes.py`
- Modify: `src/aml_guardian/persistence/repository.py`
- Modify: `src/aml_guardian/audit/chain.py`
- Modify: `tests/api/test_api.py`
- Create: `tests/api/test_alert_workflow.py`
- Create: `tests/api/test_audit_api.py`

**Interfaces:**
- `list_alert_records(state: AlertState | None, em_risco: bool | None, reference_date: date, db_path: Path | None) -> list[AlertRecord]`.
- `AuditChain.verify_details() -> {valid: bool, events_checked: int, first_invalid_seq: int | None}`.
- Rotas devem corresponder literalmente a `SPEC.md` §9.1.

- [ ] **Step 1: escrever testes RED para as rotas contratuais**

Cobrir:
- `GET /alerts?state=&em_risco=` com filtros e RBAC;
- `POST /dossiers/{id}/reidentify` para analyst/officer, `Cache-Control: no-store`, evento `PII_REVEALED`, 410 quando Vault indisponível;
- `POST /dossiers/{id}/submit` somente analyst, `DRAFT_READY → SUBMITTED`;
- `POST /dossiers/{id}/approval` somente officer e somente a partir de `SUBMITTED`;
- `DEVOLVER` faz `SUBMITTED → RETURNED`; uma edição/reabertura explícita restaura `RETURNED → DRAFT_READY` antes de nova submissão;
- `GET /audit/{id}` somente officer;
- `GET /audit/verify` retorna o primeiro `seq` inválido;
- transições inválidas retornam 409;
- justificativa menor que 50 caracteres retorna 422.

- [ ] **Step 2: separar rotas por responsabilidade**

Manter `routes.py` como agregador de routers, para respeitar o limite de arquivo. Não manter aliases de rota divergentes sem necessidade documentada.

- [ ] **Step 3: implementar API-02**

`em_risco=true` significa `prazo_interno - data_referencia <= 1 dia` para alertas ainda não aprovados. Consulta parametrizada; ordenação por prazo ascendente e `selected_at` como desempate.

- [ ] **Step 4: implementar API-04 conforme contrato**

A rota recebe `alert_id`, lê os tokens do alerta sanitizado no checkpoint e retorna o mapa completo. Todo acesso bem-sucedido grava `PII_REVEALED` sem valores. Se o Vault foi perdido, usar uma interface explícita de reconstrução a partir do sistema de origem; se a reconstrução não estiver disponível, retornar 410, nunca 404 enganoso. Sempre enviar `Cache-Control: no-store`.

- [ ] **Step 5: implementar API-05 e API-06 sem pular estados**

Persistir o estado no `AlertRecord` e atualizar o dossiê/checkpoint de forma coerente. A aprovação deve produzir DT-15 e evento de auditoria. Nenhum caminho `DRAFT_READY → APPROVED` deve existir.

- [ ] **Step 6: implementar API-07 e API-08**

`verify_details` precisa recalcular a cadeia e informar `events_checked` e `first_invalid_seq`, não apenas booleano.

- [ ] **Step 7: validar fluxo completo**

```bash
.venv/Scripts/python.exe -m pytest tests/api tests/audit tests/e2e -q
.venv/Scripts/ruff.exe check src/aml_guardian/api src/aml_guardian/audit src/aml_guardian/persistence tests/api
```

Acceptance: todas as APIs 01–09 existem com método, rota, papel, estado e resposta definidos no SPEC.

**Orchestrator commit:** `feat(api): complete human workflow and audit endpoints [RF-10 RF-12 API-02..08]`

---

### Task 4: Fechar resiliência, timeout, retry e budget do RF-10

**Files:**
- Create: `src/aml_guardian/graph/execution.py`
- Create: `src/aml_guardian/graph/budget.py`
- Modify: `src/aml_guardian/graph/build.py`
- Modify: `src/aml_guardian/investigation/runner.py`
- Modify: `src/aml_guardian/mcp_servers/client.py`
- Modify: `src/aml_guardian/graph/node_support.py`
- Modify: `tests/graph/test_graph.py`
- Create: `tests/graph/test_resilience.py`

**Interfaces:**
- `NodePolicy(timeout_seconds: float, max_retries: int = 2, backoff_seconds: tuple[float, float] = (0.1, 0.2))`.
- `BudgetTracker.consume_tokens(state, tokens_in, tokens_out) -> InvestigationState`.
- `BudgetTracker.ensure_time(state, now) -> None`, lançando exceção controlada quando exceder 40 s.
- Uma tentativa inicial + no máximo 2 retries.

- [ ] **Step 1: escrever testes RED de injeção de falha**

Cobrir timeout real, JSON inválido, MCP fora, duas falhas retryable seguidas de sucesso, três falhas, budget de tokens > 2.000, relógio > 40 s e retomada do checkpoint após interrupção. Usar relógio/sleep injetável para testes rápidos; não esperar segundos reais.

- [ ] **Step 2: centralizar políticas por nó**

Usar os orçamentos de `AGENTS.md` §1 e timeout = 2× orçamento. Erro não retryable desvia imediatamente. Erro retryable respeita backoff exponencial e incrementa `attempts[node]`.

- [ ] **Step 3: tornar timeout efetivo**

A checagem deve interromper/abandonar a chamada, não apenas medir depois que terminou. Escolher mecanismo compatível com Windows e funções síncronas existentes, mantendo o executor isolado e testável.

- [ ] **Step 4: atualizar budget pelo evento do modelo**

Somar `tokens_in + tokens_out` no estado após cada chamada. Antes de cada nó, verificar tempo desde `budget.started_at`. Excesso segue para `NEEDS_HUMAN` preservando artefatos parciais.

- [ ] **Step 5: remover falhas silenciosas da auditoria regulatória**

`audit_events` é requisito, não telemetria opcional. Falha ao gravar evento regulatório deve produzir `NEEDS_HUMAN`; apenas observabilidade dev-only pode ser best-effort. Atualizar testes.

- [ ] **Step 6: validar**

```bash
.venv/Scripts/python.exe -m pytest tests/graph tests/investigation tests/mcp_servers -q
.venv/Scripts/ruff.exe check src/aml_guardian/graph src/aml_guardian/investigation src/aml_guardian/mcp_servers tests/graph
```

Acceptance: todos os casos de RF-10/RNF-06 terminam em estado válido, sem arquivamento por falha e sem evento duplicado.

**Orchestrator commit:** `feat(graph): enforce retries timeouts and alert budgets [RF-10 RNF-06]`

---

### Task 5: Implementar o cache semântico normativo RF-04

**Files:**
- Create: `src/aml_guardian/retrieval/cache.py`
- Modify: `src/aml_guardian/retrieval/query.py`
- Modify: `src/aml_guardian/config/litellm.py`
- Modify: `config/litellm.yaml` somente se necessário para uma chave `enabled`
- Modify: `src/aml_guardian/graph/nodes_retrieval.py`
- Create: `tests/retrieval/test_cache.py`
- Modify: `tests/privacy/test_canary.py`

**Interfaces:**
- `SemanticNormCache.lookup(query: str, corpus_version: str) -> list[dict[str, object]] | None`.
- `SemanticNormCache.store(query: str, corpus_version: str, candidates: list[dict[str, object]]) -> None`.
- Entrada contém somente consulta normativa sanitizada e `corpus_version`.
- Valor contém somente `chunk_id`, `article_ref` e score; nunca `alert_id`, decisão, recomendação, evidência ou token de PII.

- [ ] **Step 1: escrever testes RED**

Cobrir miss/hit, threshold 0,92, cache desligado, troca de `corpus_version`, inspeção de metadados sem campos proibidos, e resultado de cache obrigatoriamente passando Seleção e Revisor.

- [ ] **Step 2: implementar coleção `semantic_cache`**

Reusar o cliente/embedding de `norms/store.py` sem misturar a coleção `norms`. Namespace ou metadado deve impedir hit entre versões de corpus.

- [ ] **Step 3: integrar na recuperação**

Ordem: montar query → lookup se habilitado → MCP-03 em miss → store → Seleção → Revisor. Golden de recall/grounding força `enabled=false`.

- [ ] **Step 4: ampliar canário**

Varredura precisa cobrir `norms`, `semantic_cache`, prompts, SQLite/checkpoints e logs estruturados quando existirem.

- [ ] **Step 5: validar**

```bash
.venv/Scripts/python.exe -m pytest tests/retrieval tests/review tests/privacy -q
.venv/Scripts/ruff.exe check src/aml_guardian/retrieval tests/retrieval tests/privacy
```

Acceptance: todos os critérios de RF-04 passam e a recuperação continua determinística.

**Orchestrator commit:** `feat(retrieval): add corpus-versioned semantic norm cache [RF-04]`

---

### Task 6: Corrigir recall crítico usando apenas o conjunto de desenvolvimento

**Files:**
- Create: `scripts/analyze_development_recall.py`
- Create: `src/aml_guardian/triage/calibration.py`
- Modify: `src/aml_guardian/triage/detectors.py`
- Modify: `src/aml_guardian/triage/engine.py`
- Modify: `config/triage_rules.yaml`
- Modify: `src/aml_guardian/config/triage.py`
- Create: `tests/triage/test_critical_patterns.py`
- Create: `reports/development-recall.md`
- Modify: `MEMORY.md`

**Interfaces:**
- O script lê somente a partição de desenvolvimento produzida por `sourcedata/golden.py`.
- O relatório apresenta recall por cada uma das seis tipologias críticas, taxa de investigação total e falsos positivos sobre desenvolvimento.
- Detectores continuam determinísticos e versionados; `rules_version` deve incrementar.

- [ ] **Step 1: caracterizar o conjunto de desenvolvimento sem ler payloads golden**

Executar o pipeline atual na partição de desenvolvimento e registrar matriz por tipologia: disparos por detector, desfecho e sinais observáveis em DT-04. Não usar rótulo como entrada do detector; ele serve apenas para avaliação offline.

- [ ] **Step 2: escrever testes RED a partir de padrões gerais**

Criar fixtures sintéticas mínimas, não copiadas do golden, para `Structuring`, `Smurfing`, `Deposit-Send`, `Layered Fan-In`, `Layered Fan-Out` e `Stacked Bipartite`. Cada uma deve disparar pelo comportamento transacional, não pelo nome da tipologia.

- [ ] **Step 3: corrigir causa, não memorizar amostras**

Melhorar detectores e, se necessário, o contexto determinístico permitido pelo contrato. Não incluir `alert_id`, conta específica, label SAML-D ou exceção por estrato. Se o contrato de entrada da Triagem precisar mudar, parar e registrar ADR complementar antes do código.

- [ ] **Step 4: calibrar apenas no desenvolvimento**

Escolher limiares com trade-off explícito entre recall crítico e `p_investigar`. Registrar todas as opções comparadas. O objetivo obrigatório de desenvolvimento é 100% das tipologias críticas sem tornar 100% dos alertas `INVESTIGAR`.

- [ ] **Step 5: validar sem golden**

```bash
.venv/Scripts/python.exe -m pytest tests/triage tests/features -q
.venv/Scripts/python.exe scripts/analyze_development_recall.py --output reports/development-recall.md
.venv/Scripts/ruff.exe check src/aml_guardian/triage scripts/analyze_development_recall.py tests/triage
```

Acceptance:
- 100% de recall crítico no desenvolvimento.
- Mesma entrada + mesma versão produz mesma decisão.
- Relatório inclui impacto em `p_investigar` e FP.
- Nenhuma execução golden nesta tarefa.

**Orchestrator commit:** `fix(triage): recover critical typology recall on development set [RF-03 RNF-01]`

---

### Task 7: Completar curadoria normativa e tornar Grounding mensurável

**Files:**
- Modify: `data/mappings/saml_d_to_cc4001.yaml`
- Modify: `src/aml_guardian/sourcedata/mapping.py` se a validação precisar ser endurecida
- Create: `scripts/evaluate_retrieval.py`
- Create: `tests/retrieval/test_mapping_coverage.py`
- Modify: `tests/retrieval/test_selection.py`
- Create: `reports/development-grounding.md`
- Modify: `MEMORY.md`

**Interfaces:**
- Todas as 17 tipologias suspeitas devem possuir pelo menos um `article_ref` válido e `applicability` curado, ou justificativa normativa explícita que impeça COS para aquela tipologia.
- `mapping_version` deve incrementar.
- `scripts/evaluate_retrieval.py` mede recall@5 e grounding bruto na partição de desenvolvimento com cache desligado.

- [ ] **Step 1: escrever teste RED de cobertura**

O teste falha enquanto uma tipologia suspeita capaz de resultar em `COMUNICAR` tiver `article_ref=[]` ou `applicability=null`. Cada `article_ref` deve existir no corpus vigente.

- [ ] **Step 2: curar o mapeamento contra fontes já ingeridas**

Não inventar artigo, inciso, alínea ou texto. Copiar somente referências existentes no corpus oficial e manter `applicability` como explicação curada, limitada a 300 caracteres.

- [ ] **Step 3: avaliar recuperação no desenvolvimento**

Medir recall@5 por tipologia para o modelo atual. Se o modelo de embedding não atingir cobertura suficiente, comparar o candidato previsto no ADR-009 usando exatamente o mesmo conjunto de desenvolvimento; uma troca exige novo ADR antes de alterar o modelo.

- [ ] **Step 4: validar grounding determinístico**

```bash
.venv/Scripts/python.exe -m pytest tests/norms tests/retrieval tests/review tests/dossier -q
.venv/Scripts/python.exe scripts/evaluate_retrieval.py --dataset development --cache-disabled --output reports/development-grounding.md
.venv/Scripts/ruff.exe check src/aml_guardian/retrieval src/aml_guardian/sourcedata scripts/evaluate_retrieval.py tests/retrieval
```

Acceptance:
- Grounding bruto ≥99% no desenvolvimento.
- Zero citações não verificadas em `DRAFT_READY`.
- Todas as referências passam MCP-04 e verificação SHA-256.
- Nenhuma execução golden nesta tarefa.

**Orchestrator commit:** `feat(rag): complete normative mapping and grounding coverage [RF-06 RF-07 RNF-02]`

---

### Task 8: Implementar logging estruturado e fechar o canário RNF-05/RNF-08

**Files:**
- Create: `src/aml_guardian/observability/logging.py`
- Create: `src/aml_guardian/observability/__init__.py`
- Modify: `src/aml_guardian/api/app.py`
- Modify: componentes que hoje engolem exceções regulatórias
- Modify: `tests/privacy/test_canary.py`
- Create: `tests/observability/test_logging.py`

**Interfaces:**
- `configure_logging() -> None` instala JSON formatter.
- Todo registro contém `trace_id`, `event`, `level` e timestamp.
- Nenhum registro contém payload, prompt completo, resposta completa, nome, CPF/CNPJ ou conta em claro.

- [ ] **Step 1: escrever testes RED**

Capturar logs dos caminhos de sucesso e falha. Validar JSON por linha, presença de `trace_id` e ausência dos canários marcados.

- [ ] **Step 2: implementar logging mínimo**

Registrar fronteiras e falhas com identificadores/hashes. Não duplicar a trilha regulatória; `audit_events` continua fonte oficial.

- [ ] **Step 3: ampliar canário para todos os destinos**

Cobrir prompt capturado, logs, `audit_events`, `alert_records`, checkpoint SQLite, Chroma `norms` e `semantic_cache`.

- [ ] **Step 4: validar**

```bash
.venv/Scripts/python.exe -m pytest tests/privacy tests/observability -q
.venv/Scripts/ruff.exe check src/aml_guardian/observability tests/observability tests/privacy
```

Acceptance: zero ocorrência em todos os destinos e 100% dos logs de aplicação em JSON com `trace_id`.

**Orchestrator commit:** `feat(observability): add pii-safe structured logging [RNF-05 RNF-08]`

---

### Task 9: Construir a UI Streamlit e o E2E Playwright

**Files:**
- Create: `src/aml_guardian/ui/app.py`
- Create: `src/aml_guardian/ui/api_client.py`
- Create: `src/aml_guardian/ui/session.py`
- Create: `src/aml_guardian/ui/__init__.py`
- Create: `tests/ui/test_api_client.py`
- Create: `tests/e2e/test_ui_workflow.py`
- Modify: `pyproject.toml` para entry point opcional se necessário

**Interfaces:**
- UI consome exclusivamente API REST.
- `ApiClient` oferece listagem, detalhe, reidentificação, submissão e aprovação.
- Valor reidentificado existe somente em `st.session_state` e é apagado ao trocar de alerta/sessão; nenhum cache persistente.

- [ ] **Step 1: escrever testes RED do cliente HTTP**

Validar rotas API-02 a API-06, cabeçalhos de papel, tratamento de 401/403/404/409/410/422 e `Cache-Control: no-store`.

- [ ] **Step 2: implementar fila e detalhe**

Fila filtrável por estado e `em_risco`, ordenada por prazo. Detalhe exibe dossiê mascarado e marca campos gerados por IA.

- [ ] **Step 3: implementar reidentificação e fluxo humano**

Botão explícito de reidentificação, submissão pelo analyst e decisão pelo officer com justificativa ≥50 caracteres. Nunca imprimir token de autenticação ou valor real em log.

- [ ] **Step 4: implementar Playwright E2E**

Subir API e Streamlit em portas de teste, criar alerta sintético, abrir fila, visualizar dossiê, reidentificar, submeter e aprovar. O teste deve inspecionar logs temporários e confirmar ausência do PII marcado.

- [ ] **Step 5: validar**

```bash
.venv/Scripts/python.exe -m pytest tests/ui -q
.venv/Scripts/python.exe -m pytest tests/e2e/test_ui_workflow.py -q
.venv/Scripts/ruff.exe check src/aml_guardian/ui tests/ui tests/e2e/test_ui_workflow.py
```

Acceptance: RF-13 e o fluxo completo alerta → decisão passam pelo navegador, sem acesso direto da UI a SQLite/Chroma/Vault.

**Orchestrator commit:** `feat(ui): deliver analyst and officer workflow [RF-12 RF-13]`

---

### Task 10: Fechar SAST, dependências e DAST

**Files:**
- Create: `scripts/security_scan.py`
- Create: `config/semgrep.yaml` apenas para regras locais justificadas
- Create: `reports/security-final.md`
- Modify: `pyproject.toml` se comandos/extra precisarem ser alinhados
- Modify: `MEMORY.md`

**Interfaces:**
- Um comando produz resultado agregado para Bandit, pip-audit, Semgrep e ZAP baseline.
- Exceções devem citar ID da regra, local, justificativa e risco residual; não usar exclusão global.

- [ ] **Step 1: tornar a execução reproduzível**

No Windows, Semgrep e ZAP podem rodar via Docker/WSL. O script deve detectar indisponibilidade e falhar com instrução objetiva; nunca marcar ferramenta ausente como aprovada.

- [ ] **Step 2: executar as quatro ferramentas**

Usar a API local com autenticação de teste no ZAP. Corrigir achados reais, mantendo tokens apenas em variáveis de ambiente do processo de teste.

- [ ] **Step 3: registrar evidência**

`reports/security-final.md` deve conter comandos, versões, contagens por severidade e disposição dos achados.

- [ ] **Step 4: validar gate**

```bash
.venv/Scripts/python.exe scripts/security_scan.py --report reports/security-final.md
```

Acceptance: 0 High/Critical abertos em SAST, dependências e DAST.

**Orchestrator commit:** `chore(security): verify sast dependencies and dast [RNF-07]`

---

### Task 11: Criar documentação de execução, demonstração e CI

**Files:**
- Create: `README.md`
- Create: `.github/workflows/ci.yml`
- Create: `.env.example` somente com nomes e valores fictícios não secretos
- Create: `docs/DEMO.md`
- Create: `docs/ARCHITECTURE.md`
- Modify: `.gitignore` se necessário

**Interfaces:**
- README oferece setup reproduzível no Windows/Git Bash com Python 3.13 da `.venv`, Ollama e modelos necessários.
- CI roda somente gates offline; não baixa dataset gigante nem depende de Ollama.

- [ ] **Step 1: escrever README orientado a avaliador**

Incluir problema, valor de negócio, arquitetura, guardrails, stack, estado Go/No-Go real, instalação, execução API/UI, testes, avaliação, segurança, estrutura do repositório, limitações e licença SAML-D não comercial. Não alegar gate ainda não aprovado.

- [ ] **Step 2: documentar demo**

Roteiro de 5–10 minutos: iniciar Ollama, API e Streamlit; ingerir alerta sintético; mostrar triagem, dossiê/citação, auditoria, reidentificação e decisão humana.

- [ ] **Step 3: documentar arquitetura sem duplicar toda a SPEC**

Usar diagrama Mermaid, limites de confiança, fluxo de dados e decisões ADR relevantes. Referenciar documentos canônicos.

- [ ] **Step 4: criar CI offline**

Workflow em Python suportado que instala `[dev]`, executa Ruff, testes offline, Bandit e pip-audit. Cachear dependências. Falhar em High/Critical; registrar explicitamente advisories sem fix se ainda existirem.

- [ ] **Step 5: validar comandos copiados**

Executar localmente todos os comandos do README antes de declarar documentação concluída.

**Orchestrator commit:** `docs: add reproducible setup demo and CI`

---

### Task 12: Rodar validação integrada e a única nova avaliação golden

**Files:**
- Modify: `scripts/evaluate.py` somente se métricas ainda não refletirem o SPEC literal
- Create: `reports/eval-final-<data>.json`
- Create: `reports/eval-final-<data>.md`
- Modify: `MEMORY.md`
- Modify: `tasks/M2-M7.md`
- Modify: `TASKS.md` apenas para atualizar estado/versão, sem reescrever requisitos

**Interfaces:**
- Relatório final contém os 9 gates do SPEC §10, versões, parâmetros, tamanho da amostra, hardware e origem de cada medida.
- Grounding deve ser “medida” somente se houve citações propostas; denominador zero não é aprovação.

- [ ] **Step 1: executar todos os gates offline frescos**

```bash
.venv/Scripts/ruff.exe check src tests scripts
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m pip check
.venv/Scripts/bandit.exe -q -r src
.venv/Scripts/pip-audit.exe
```

Esperado: 0 falhas. Registrar contagem real, não reutilizar a contagem desta auditoria.

- [ ] **Step 2: executar E2E e segurança externa**

```bash
.venv/Scripts/python.exe -m pytest tests/e2e/test_ui_workflow.py -q
.venv/Scripts/python.exe scripts/security_scan.py --report reports/security-final.md
```

- [ ] **Step 3: confirmar Ollama e executar smoke test limitado**

Usar `--limit` apenas para verificar infraestrutura, sem tomar decisão de limiar. Corrigir somente falhas mecânicas do harness.

- [ ] **Step 4: executar a rodada golden completa uma vez**

```bash
.venv/Scripts/python.exe scripts/evaluate.py --golden data/golden/v1 --ollama
```

Renomear/copiar os artefatos gerados para `eval-final-<data>.json/.md` sem alterar resultados.

- [ ] **Step 5: executar portabilidade RNF-10 com o alias alternativo**

A mesma suíte deve aceitar troca apenas em `config/litellm.yaml`. Registrar modelo, duração e resultado; não chamar isso de provedor cloud.

- [ ] **Step 6: atualizar estado do projeto honestamente**

Se todos os gates passarem, registrar Go. Se qualquer gate obrigatório falhar, registrar No-Go com valores e causa; não ajustar novamente olhando exemplos golden. Atualizar `MEMORY.md`, `tasks/M2-M7.md`, README e relatório para o mesmo estado.

- [ ] **Step 7: revisão final do diff e histórico**

```bash
git status --short
git diff --check
git diff --stat
```

Acceptance:
- todos os requisitos nomeados neste plano têm teste ou relatório correspondente;
- working tree contém somente artefatos intencionais;
- nenhuma credencial, PII ou banco foi adicionado;
- status Go/No-Go é consistente em README, MEMORY, TASKS e relatório.

**Orchestrator commit:** `chore(release): record final poc verification [SPEC-10 RNF-01..10]`

---

## Comandos de regressão por lote

Para evitar o timeout observado na suíte monolítica, Codex pode usar estes lotes durante desenvolvimento:

```bash
.venv/Scripts/python.exe -m pytest -q tests/contracts tests/config tests/test_stack.py
.venv/Scripts/python.exe -m pytest -q tests/api tests/audit tests/e2e tests/graph tests/privacy tests/scripts
.venv/Scripts/python.exe -m pytest -q tests/deadlines tests/dossier tests/features tests/investigation tests/mcp_servers tests/norms tests/retrieval tests/review tests/sanitizer tests/triage
.venv/Scripts/python.exe -m pytest -q tests/sourcedata
```

A validação final ainda deve executar `pytest -q` completo com timeout suficiente.

## Contrato de saída para cada execução do Codex

```xml
<structured_output_contract>
Relate exatamente:
1. causa/objetivo atendido e decisões tomadas;
2. arquivos alterados;
3. testes escritos e ciclo RED/GREEN observado;
4. comandos executados, exit codes e contagens reais;
5. riscos, desvios ou requisitos ainda não atendidos;
6. confirme que não executou git add, commit ou push.
</structured_output_contract>
```

## Ordem obrigatória

`Task 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12`.

Não paralelizar Tasks 2–8: elas alteram contratos, estado, auditoria e métricas que dependem umas das outras. Task 11 pode começar após Task 9, mas deve ser revisada novamente após Task 12 para refletir o estado final.