# AGENTS — Agentic AML & Regulatory Compliance Guardian

| Campo | Valor |
| :--- | :--- |
| Versão | 1.0.0 |
| Status | Aprovado |
| Origem | `INTENT.md` · `SPEC.md` 1.1.0 · `SOUL.md` 1.0.0 (todos aprovados em 2026-09-15) |
| Decisões vinculadas | `docs/ADR.md` — ADR-001 a ADR-013 |
| Evidência reutilizada | `scripts/bench_ollama.py` · `reports/benchmark-ollama-2026-09-15-v2.md` |
| Próximos documentos | `PLAN.md` → `TASKS.md` |
| Gate | Aprovado por: marcosjcn94@gmail.com — Data: 2026-09-15 |

Convenção: **MUST** = obrigatório; **MUST NOT** = proibido (igual ao `SPEC.md`).
Este documento define **papel, entrada, saída, tools, modelo e prompt** de cada agente. Ele herda integralmente os princípios P1–P6
e as fronteiras Always / Ask First / Never do `SOUL.md`, que não são repetidos aqui. Toda regra aponta para a sua origem.
"Agente" = nó do grafo LangGraph ou componente do perímetro que troca mensagens DT-14. Só a Investigação usa LLM (ADR-013).

---

## 1. Mapa dos agentes de runtime

| Nó | Tipo | Estado (RF-10) | Entrada → Saída | Tools MCP | Modelo | Orçamento p95 (SPEC §5) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Sanitizador | Determinístico (perímetro, fora do grafo) | `RECEIVED → SANITIZED` | DT-01 → DT-04 | — | — | Grupo A ≤ 1,5 s |
| Triagem | Determinístico | `SANITIZED → TRIAGED` | DT-04 → DT-06 | MCP-02 | — | Grupo A |
| Investigação | Pré-passo determinístico + LLM | `TRIAGED → INVESTIGATING → RESEARCHING` | DT-04 + DT-06 → DT-16 + DT-07 | MCP-01, MCP-02 (só no pré-passo) | `qwen2.5:1.5b` Q4 | Pré-passo no Grupo A; LLM ≤ 14 s |
| Recuperação | Determinístico | `RESEARCHING` | DT-07 → `retrieved_chunk_ids[]` | MCP-03 | — (embedding FastEmbed) | ≤ 0,5 s |
| Seleção de chunks | Determinístico | `RESEARCHING → REVIEWING` | `retrieved_chunk_ids[]` → DT-09 (≤ 3) | MCP-04 | — | ≤ 0,5 s |
| Revisor | Determinístico | `REVIEWING` | DT-09 → DT-10 | MCP-04 | — | Grupo B ≤ 1 s |
| Dossiê + Prazo | Determinístico (Jinja2) | `REVIEWING` ou `TRIAGED` (`PROPOR_ARQUIVAMENTO`) `→ DRAFT_READY` | DT-06/07/09/10/16 → DT-11 | — | — | Grupo B |
| Encaminhamento humano | Determinístico | qualquer estado anterior a `DRAFT_READY` `→ NEEDS_HUMAN` | DT-14 `ERROR` → DT-05 com `failure_reason` | — | — | — |

- Grupo A = sanitização + triagem + chamadas MCP de dados + cálculo de indicadores; Grupo B = revisor + template + auditoria (SPEC §5).
- Timeout por nó = 2 × orçamento do nó ou do grupo; no máximo 2 retries com backoff exponencial (RF-10).
- Orçamento por alerta: ≤ 2.000 tokens e ≤ 40 s de relógio; excedido → `NEEDS_HUMAN` (RF-10).
- **Auditoria é transversal:** todo nó MUST emitir DT-12 idempotente (`event_key = alert_id + node + attempt`) e salvar checkpoint ao terminar (RF-10, RF-11).

---

## 2. Fichas dos agentes de runtime

### 2.1 Sanitizador
- **Papel:** tokenizar dado pessoal antes de persistência, inferência ou vetorização (RF-02, ADR-003, ADR-012).
- **Entrada:** DT-01 recebido pela API-01. Também recebe a saída bruta de MCP-01 e MCP-02 antes de ela chegar a um agente (RF-02).
- **Saída:** DT-04 (`pii_token_count`, `sanitizer_version`). O mapa token → valor vai só para o Vault.
- **Proibido:** liberar texto com detecção ambígua; persistir o payload bruto (RF-01); logar valor real.
- **Falha → destino:** exceção ou ambiguidade → `NEEDS_HUMAN`, sem chamar LLM (fail-closed).
- **Auditoria:** `ALERT_RECEIVED`, transição `RECEIVED → SANITIZED` com `sanitizer_version`.
- **Aceite:** RF-02 (recall ≥ 99% CPF/CNPJ/conta, ≥ 95% nomes; canário RNF-05).

### 2.2 Triagem
- **Papel:** decidir `PROPOR_ARQUIVAMENTO` ou `INVESTIGAR` por regra versionada (RF-03, ADR-004).
- **Entrada:** DT-04.
- **Saída:** DT-06 (`fired_rules[]{rule_id, description, critical}`, `rules_version`).
- **Tools:** MCP-02, que alimenta o detector "acerto em lista de restrição" (RF-03).
- **Proibido:** `PROPOR_ARQUIVAMENTO` com qualquer detector crítico disparado; usar LLM; ajustar regras com o golden set (SPEC §8.3).
- **Falha → destino:** erro de regra ou MCP-02 indisponível após retries → `NEEDS_HUMAN` (nunca arquivamento).
- **Versões gravadas:** `rules_version`.
- **Aceite:** RF-03 (0 críticos com `PROPOR_ARQUIVAMENTO`; determinismo por `rules_version`).

### 2.3 Investigação
- **Papel:** propor hipótese de tipologia, confiança, recomendação e evidências (RF-05). É o único nó LLM (ADR-013).
- **Entrada:** DT-04 + DT-06.
- **Pré-passo determinístico (código, não modelo):** chama MCP-01 (`window_days = 180`) e MCP-02, passa as saídas pelo Sanitizador e calcula o DT-16 segundo o catálogo da §4.3.
- **Chamada LLM:** prompt v1 (§4.1) via LiteLLM, schema de geração imposto (§4.2). O modelo **não** chama tool, não recebe a lista bruta de transações e não escreve texto livre.
- **Saída:** DT-16 + DT-07 expandido (§4.2).
- **Pós-processamento determinístico (RF-05):**
  - descartar `feature_id` inexistente no DT-16 e registrar o descarte;
  - detector crítico disparado na triagem, ou `typology_hypothesis` crítica (SPEC §3.2) com `ARQUIVAR` → `NEEDS_HUMAN`;
  - `INCONCLUSIVO` segue para `NEEDS_HUMAN` na montagem do dossiê (RF-08).
- **Proibido:** texto do dossiê, citação normativa, estado final do alerta (SOUL §3.1); fallback para modelo maior (RF-10).
- **Falha → destino:** JSON inválido após 2 retries, timeout (2 × 14 s), orçamento de tokens/tempo esgotado ou MCP indisponível → `NEEDS_HUMAN`.
  Não existe modelo menor validado para fallback (ADR-013 B).
- **Auditoria:** `TOOL_CALLED` por chamada MCP; evento do nó com `model_id`, `prompt_sha256`, `prompt_version`, `tokens_in`, `tokens_out`, `latency_ms` (RF-11). O prompt completo nunca é logado.
- **Versões gravadas:** `prompt_version`, `features_version`, `model`.
- **Aceite:** RF-05 (100% válido no schema ou `NEEDS_HUMAN`; 0 evidências com referência inexistente).

### 2.4 Recuperação
- **Papel:** buscar candidatos normativos para a hipótese (RF-06, ADR-009).
- **Entrada:** `typology_hypothesis` (DT-07) + incisos mapeados em `data/mappings/saml_d_to_cc4001.yaml`.
- **Processo:** consulta montada por template, sem dado pessoal. Primeiro consulta o cache semântico (RF-04: cosseno ≥ `cache.threshold`, mesma `corpus_version`); se não houver acerto, chama MCP-03 com `top_k = 8`.
- **Saída:** `retrieved_chunk_ids[]` com `article_ref` e `score`.
- **Proibido:** guardar no cache decisão, recomendação, evidência ou `alert_id` (RF-04); pular o Revisor em resultado de cache.
- **Falha → destino:** MCP-03 indisponível após retries → `NEEDS_HUMAN`.
- **Versões gravadas:** `corpus_version`, `mapping_version`.
- **Aceite:** RF-04 (troca de `corpus_version` zera acertos; coleção de cache sem PII nem decisão).

### 2.5 Seleção de chunks
- **Papel:** escolher até 3 `chunk_id` entre os recuperados (RF-06, ADR-013 A).
- **Entrada:** `retrieved_chunk_ids[]`.
- **Processo:** lê o texto de cada candidato via MCP-04. Prioriza os `article_ref` preferenciais da tipologia no mapeamento, desempata por RRF (vetorial × BM25) e descarta abaixo de `selection.min_score`.
- **Saída:** DT-09 com `quoted_text` copiado do chunk e `applicability` copiado do texto curado do mapeamento (≤ 300 caracteres).
- **Proibido:** gerar, parafrasear ou completar texto normativo; propor `chunk_id` fora do conjunto recuperado; usar LLM.
- **Falha → destino:** erro ou MCP-04 indisponível → `NEEDS_HUMAN`.
- **Aceite:** RF-06 (grounding bruto ≥ 99%, RNF-02).

### 2.6 Revisor
- **Papel:** verificar cada citação por hash (RF-07).
- **Entrada:** DT-09.
- **Processo:** confirma via MCP-04 que o `chunk_id` pertence à `corpus_version` vigente e que o SHA-256 do trecho normalizado (NFC, espaços colapsados, trim) é igual a `text_sha256`.
- **Saída:** DT-10 (`verified_citations[]`, `rejected_citations[]{chunk_id, reason}`, `grounding_raw_ratio`).
- **Proibido:** corrigir citação rejeitada; usar LLM.
- **Falha → destino:** minuta `COS` sem nenhuma citação verificada → `NEEDS_HUMAN`.
- **Aceite:** RF-07 (0 não verificadas em `DRAFT_READY`; citação com 1 caractere adulterado é rejeitada).

### 2.7 Dossiê + Prazo
- **Papel:** montar a minuta por template e calcular prazos (RF-08, RF-09).
- **Entrada:** DT-06, DT-07, DT-09 verificadas (DT-10), DT-16. No caminho `PROPOR_ARQUIVAMENTO`, só DT-06.
- **Saída:** DT-11 `COS` ou `ARQUIVAMENTO`, com `ai_generated_fields = [typology_hypothesis, confidence, recommendation, evidence_feature_ids]` marcados "gerado por IA".
  Também persiste `prazo_interno`, `prazo_regulatorio_analise` e a sinalização `EM_RISCO`.
- **Proibido:** incluir texto livre de LLM; incluir citação não verificada; chegar a estado posterior a `DRAFT_READY`.
- **Falha → destino:** campo obrigatório do DT-11 ausente ou recomendação `INCONCLUSIVO` → `NEEDS_HUMAN`.
- **Versões gravadas:** `versions{rules, corpus, mapping, features, prompt, model}`.
- **Aceite:** RF-08 (snapshot do template; 100% válido no DT-11) e RF-09 (fronteiras de calendário).

### 2.8 Encaminhamento humano
- **Papel:** estado terminal seguro de falha (RF-10, ADR-011).
- **Entrada:** qualquer DT-14 do tipo `ERROR`, ou gatilho do SOUL §3.3.
- **Saída:** DT-05 com `state = NEEDS_HUMAN` e `failure_reason`. Preserva tudo o que o `InvestigationState` já acumulou.
- **Proibido:** arquivar, descartar produção parcial, reprocessar automaticamente.
- **Aceite:** RF-10 (injeção de falha termina em estado válido, sem arquivamento e sem evento duplicado).

---

## 3. Matriz tools × agentes

| Tool | Sanitizador | Triagem | Investigação (pré-passo) | Investigação (LLM) | Recuperação | Seleção | Revisor | Dossiê | Encaminhamento |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| MCP-01 `get_customer_history` | — | — | ✅ | — | — | — | — | — | — |
| MCP-02 `check_restriction_lists` | — | ✅ | ✅ | — | — | — | — | — | — |
| MCP-03 `search_norms` | — | — | — | — | ✅ | — | — | — | — |
| MCP-04 `get_norm_passage` | — | — | — | — | — | ✅ | ✅ | — | — |

- O que não está marcado é negado. Dado só via MCP e modelo só via LiteLLM (SOUL P6, RNF-10).
- Regras comuns (SPEC §9.2): timeout 2 s, erro `{error_code, retryable}`, evento `TOOL_CALLED` com hash da entrada.
- MCP-01 e MCP-02 são sanitizados na saída (RF-02). MCP-03 só aceita consulta sanitizada.

---

## 4. Investigação — contrato congelado (v1)

### 4.1 Prompt (`prompt_version = 1`)

Instruções fixas: texto exato de `INVESTIGATION_INSTRUCTIONS` em `scripts/bench_ollama.py:58-62`, com `MAX_EVIDENCE = 3`. Sem acentos, como foi medido.

```text
No de Investigacao PLD/FT. Dados sanitizados: pessoas e contas so como tokens sinteticos.
Responda JSON: t=tipologia mais provavel ou NENHUMA; c=confianca 0-1; r=recomendacao; e=ate 3 numeros de feature que sustentam t (F03 -> 3).
```

Bloco do alerta, em seguida, no formato de `bench_ollama.py:152-156`:

```text
Alerta {alert_ref} regra {source_rule_id} titular {token_titular} conta {token_conta}
Triagem: {detectores disparados separados por virgula} disparou.
Indicadores:
F01 tx_janela={valor}
...
```

- `{alert_ref}` = 8 primeiros caracteres do `alert_id`; tokens do titular e da conta vêm do DT-04 (`CPF_01`, `CONTA_01`). Sem detector disparado: `Triagem: nenhum detector disparou.`
- **Prefixo estável:** instruções primeiro e sem nonce, para o Ollama reaproveitar o KV cache entre alertas. O nonce existe só no benchmark (`bench_ollama.py:160`).
- **Teto de 300 tokens de entrada (RF-05):**
  - o montador conta tokens com o tokenizador do modelo via LiteLLM antes da chamada;
  - acima do teto, remove as contrapartes F14+ de menor `brl`, uma por vez, em ordem determinística (empate: maior `feature_id` sai primeiro);
  - F01–F13 nunca são removidas; se ainda exceder → `NEEDS_HUMAN` sem chamar o modelo.
  - Motivo: o benchmark mediu 319 tokens de média com contrapartes calibradas.

### 4.2 Schema de geração e expansão

Schema imposto na geração (`bench_ollama.py:164-177`). `{feature_ids_presentes}` são os números das features que ficaram no prompt:

```json
{
  "type": "object",
  "properties": {
    "t": {"type": "string", "enum": ["Fan-Out", "Fan-In", "Cycle", "Bipartite", "Stacked Bipartite", "Scatter-Gather", "Gather-Scatter", "Layered Fan-In", "Layered Fan-Out", "Structuring", "Smurfing", "Over-Invoicing", "Deposit-Send", "Cash Withdrawal", "Single Large Transaction", "Behavioural Change 1", "Behavioural Change 2", "NENHUMA"]},
    "c": {"type": "number", "minimum": 0, "maximum": 1},
    "r": {"type": "string", "enum": ["COMUNICAR", "ARQUIVAR", "INCONCLUSIVO"]},
    "e": {"type": "array", "items": {"type": "integer", "enum": "{feature_ids_presentes}"}, "maxItems": 3}
  },
  "required": ["t", "c", "r", "e"]
}
```

- **Expansão para DT-07 (`bench_ollama.py:56, 190-191`):** `t → typology_hypothesis`, `c → confidence`, `r → recommendation`, `e → evidence_feature_ids` (`3 → "F03"`).
- **Validação** (`validate_output`, `bench_ollama.py:180-200`): chaves exatas, `e` só com inteiros e cada evidência ∈ DT-16.
- **Parâmetros** (ADR-013, relatório v2): `temperature 0`, `seed 42`, `num_ctx 2048`, `num_predict 60`, `num_thread 8`. O nome do modelo é um alias de configuração do LiteLLM (ADR-010).

### 4.3 Catálogo de indicadores (`features_version = 1`)

Nomes e formatos de `bench_ollama.py:128-146`. Os valores são inteiros, exceto F11, porque cada dígito custa um token no Qwen.

| ID | Nome | Cálculo | Fonte |
| :--- | :--- | :--- | :--- |
| F01 | `tx_janela` | Nº de transações do alerta em `occurrence_window` | DT-04 |
| F02 | `total_brl` | Soma de `amount_brl` na janela, arredondada para inteiro | DT-04 |
| F03 | `abaixo_limiar` | Nº de transações abaixo do limiar do detector de fragmentação | DT-04 + `config/triage_rules.yaml` |
| F04 | `dep_especie` | Nº de transações `ESPECIE_DEPOSITO` | DT-04 |
| F05 | `saida_pix_ted` | Nº de transações de saída `PIX` ou `TED` | DT-04 |
| F06 | `contrap_entrada` | Nº de contas distintas que enviaram ao titular | DT-04 |
| F07 | `contrap_saida` | Nº de contas distintas que receberam do titular | DT-04 |
| F08 | `camadas` | Profundidade fan-in/fan-out apurada pelo detector de camadas | DT-06 (RF-03) |
| F09 | `transfronteira` | Nº de transações com `sender_location ≠ receiver_location` ou `TRANSFERENCIA_INTERNACIONAL` | DT-04 |
| F10 | `especie_depois_exterior` | `sim`/`nao` — detector "depósito em espécie seguido de envio transfronteiriço" | DT-06 (RF-03) |
| F11 | `vol_vs_media180d` | Volume da janela ÷ média de volume para janelas de mesma duração nos 180 dias anteriores, 1 casa decimal + `x` | MCP-01 |
| F12 | `dias_ativos` | Nº de dias distintos com transação na janela | DT-04 |
| F13 | `listas` | `pep:sim/nao,ceis:sim/nao,cnep:sim/nao` | MCP-02 |
| F14+ | `CONTA_nn in= out= brl=` | Por contraparte (token): nº de transações recebidas dela, nº enviadas a ela e volume total inteiro. Ordenadas por `brl` decrescente | DT-04 |

- Cada feature carrega `transaction_ids[]` (DT-16). O dossiê anexa essas transações pelo código, não pelo LLM (RF-05).
- Tipologia nova exige indicador novo e incremento de `features_version` (ADR-013, riscos).

---

## 5. Envelope A2A por aresta (DT-14)

| `from_node` → `to_node` | `type` | `payload` | Condição |
| :--- | :--- | :--- | :--- |
| `sanitizer` → `triage` | `TASK` | DT-04 | Sanitização concluída |
| `triage` → `dossier` | `TASK` | DT-06 | `PROPOR_ARQUIVAMENTO` |
| `triage` → `investigation` | `TASK` | DT-04 + DT-06 | `INVESTIGAR` |
| `investigation` → `retrieval` | `RESULT` | DT-16 + DT-07 | Pós-processamento sem desvio |
| `retrieval` → `selection` | `RESULT` | `retrieved_chunk_ids[]` | — |
| `selection` → `reviewer` | `RESULT` | DT-09[] | — |
| `reviewer` → `dossier` | `RESULT` | DT-10 | Ao menos 1 citação verificada |
| qualquer nó → `human_handoff` | `ERROR` | `{failure_reason, node, attempt}` | Falha, orçamento, fail-closed ou gatilho do SOUL §3.3 |

- `payload` MUST validar contra o schema do tipo em `schema_version`. Transporte em processo na PoC, com o mesmo contrato de um transporte em rede (SPEC §9.3).
- Nenhum envelope carrega dado pessoal (DT-14). `trace_id` é o mesmo do `InvestigationState`.

---

## 6. Parte B — Agentes de desenvolvimento (execução do `TASKS.md`)

Valem integralmente o `SOUL.md` §4 e o `CLAUDE.md`. Uma tarefa do `TASKS.md` = uma fatia vertical = uma sessão de implementação.

| Papel | Quando acionar | Entrada | Saída | Pode | MUST NOT |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Implementador TDD (`ecc:tdd-guide` / `superpowers:test-driven-development`) | Toda tarefa com código | Tarefa do `TASKS.md` com IDs de requisito | Teste focado vermelho → verde, diff mínimo | Criar e editar código e testes da tarefa | Mudar contrato, regra, limiar, prompt ou dependência sem Ask First (SOUL §4) |
| Revisor Python (`ecc:python-reviewer`) | Após cada tarefa com código | Diff da tarefa | Achados priorizados | Ler e rodar teste focado | Editar código |
| Guardião de privacidade e segurança (`ecc:security-reviewer`) | Obrigatório se a mudança toca sanitizador, logging, prompt, cache, Vault ou servidor MCP | Diff + teste canário RNF-05 | Veredito e achados | Rodar canário, bandit, semgrep, pip-audit | Desativar teste, hook ou SAST para passar (RNF-07) |
| Revisor de RAG (`ecc:rag-pipeline-reviewer`) | Mudança em corpus, chunking, Recuperação, Seleção ou cache | Diff + métricas de grounding | Achados | Medir recall@5 e grounding bruto no conjunto de desenvolvimento | Usar o golden set para ajuste (SPEC §8.3) |
| Avaliador | Fim de marco do `PLAN.md` | `scripts/evaluate.py --golden data/golden/v1` | `reports/eval-<data>.json` e `.md` com os gates do SPEC §10 | Rodar e reportar | Relaxar gate sem ADR; alterar regras após ver o golden set |

- Todo commit e toda tarefa citam o ID tocado (`RF`, `RNF`, `API`, `MCP`, `DT`). Commit, push e branch são Ask First (SOUL §4).
- Dados de teste são sintéticos e gerados em tempo de execução; documento de identificação aparece só como token.

---

## 7. Governança deste documento

- **Precedência:** `SOUL.md` §5. Este documento não pode afrouxar nenhum limite do `SOUL.md` ou do `SPEC.md`.
- **Ask First:** alterar prompt, schema de geração, catálogo de indicadores, matriz de tools, envelope ou orçamento de nó.
- **Versionamento:** mudança no prompt incrementa `prompt_version`; mudança no catálogo incrementa `features_version`.
  Toda mudança incrementa a versão deste documento. Decisão estrutural gera ADR novo antes do código.
- **Reavaliação:** mudar prompt, catálogo ou modelo exige nova rodada do benchmark de latência (RNF-03) e dos gates do SPEC §10.

## Gate
Status: aprovado pelo autor em 2026-09-15. `PLAN.md` herda estes papéis, contratos e fronteiras como ponto de partida.
