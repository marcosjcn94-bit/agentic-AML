# Registro de Decisões Arquiteturais (ADR)

Este documento centraliza todas as decisões técnicas, escolhas de design e trade-offs assumidos no projeto **Agentic AML & Regulatory Compliance Guardian**.

## 📊 Índice de Decisões

| ID | Título | Data | Status |
| :--- | :--- | :--- | :--- |
| ADR-001 | [Seleção do Caso de Uso de IA: Plataforma de Investigação Autônoma de Compliance AML/BACEN](#adr-001-seleção-do-caso-de-uso-de-ia-plataforma-de-investigação-autônoma-de-compliance-amlbacen) | 2026-09-15 | Aceito |
| ADR-002 | [Orquestração Multiagente A2A e Protocolo MCP sem Vendor Lock-in](#adr-002-orquestração-multiagente-a2a-e-protocolo-mcp-sem-vendor-lock-in) | 2026-09-15 | Aceito |
| ADR-003 | [Arquitetura Zero-Trust com Mascaramento de PII no Perímetro](#adr-003-arquitetura-zero-trust-com-mascaramento-de-pii-no-perímetro) | 2026-09-15 | Aceito |
| ADR-004 | [Estratégia FinOps e Economia de Tokens via Triagem Híbrida e Cache Semântico](#adr-004-estratégia-finops-e-economia-de-tokens-via-triagem-híbrida-e-cache-semântico) | 2026-09-15 | Aceito |
| ADR-005 | [Estratégia de Dados: Corpus Normativo Público e Transações Sintéticas](#adr-005-estratégia-de-dados-corpus-normativo-público-e-transações-sintéticas) | 2026-09-15 | Aceito |
| ADR-006 | [Fronteira entre Agentes LLM e Código Determinístico](#adr-006-fronteira-entre-agentes-llm-e-código-determinístico) | 2026-09-15 | Aceito |
| ADR-007 | [API REST, UI do Analista e Autenticação da PoC](#adr-007-api-rest-ui-do-analista-e-autenticação-da-poc) | 2026-09-15 | Aceito |
| ADR-008 | [Persistência em SQLite e Trilha de Auditoria com Hash-Chain](#adr-008-persistência-em-sqlite-e-trilha-de-auditoria-com-hash-chain) | 2026-09-15 | Aceito |
| ADR-009 | [Stack de RAG Local e Escopo do Cache Semântico](#adr-009-stack-de-rag-local-e-escopo-do-cache-semântico) | 2026-09-15 | Aceito |
| ADR-010 | [Estratégia de Modelos SLM-First com Saída Estruturada via LiteLLM](#adr-010-estratégia-de-modelos-slm-first-com-saída-estruturada-via-litellm) | 2026-09-15 | Aceito |
| ADR-011 | [Recuperação de Falhas com Máquina de Estados e Checkpoint](#adr-011-recuperação-de-falhas-com-máquina-de-estados-e-checkpoint) | 2026-09-15 | Aceito |
| ADR-012 | [Gestão de Chaves, Reidentificação e Observabilidade sem PII](#adr-012-gestão-de-chaves-reidentificação-e-observabilidade-sem-pii) | 2026-09-15 | Aceito |

---

## 🛑 Histórico de Decisões

### ADR-001: Seleção do Caso de Uso de IA: Plataforma de Investigação Autônoma de Compliance AML/BACEN
- **Data:** 2026-09-15
- **Status:** Aceito

#### Contexto e Problema
A conformidade regulatória no setor bancário exige a investigação rigorosa de transações atípicas para Prevenção à Lavagem de Dinheiro e Financiamento ao Terrorismo (PLD/FT), conforme as diretrizes do BACEN (Circ. 3.978/2020) e COAF. Sistemas legados baseados em regras rígidas geram uma taxa massiva de falsos positivos (entre 90% e 95%), sobrecarregando os analistas de compliance e criando riscos de autuações regulatórias por atrasos de comunicação. É necessário um sistema inteligente que automatize a investigação e a fundamentação de alertas, reduzindo o esforço manual sem comprometer o rigor normativo.

#### Alternativas Consideradas
* **Opção 1:** Copiloto de Underwriting e Análise de Risco de Crédito PJ.
* **Opção 2:** Plataforma Autônoma de Investigação de Alertas e Compliance AML/BACEN.
* **Opção 3:** Sistema Multiagente de Regulação e Prevenção à Fraude em Sinistros de Seguros.
* **Opção 4:** Conciliador Autônomo de Disputas de Pagamento e Chargebacks.
* **Opção 5:** Copiloto de Assessoria de Investimentos & Suitability CVM.

#### Decisão Selecionada
Escolheu-se a **Opção 2 (Plataforma Autônoma de Investigação de Alertas e Compliance AML/BACEN)**. Esta escolha alinha-se perfeitamente com a atuação da CI&T nos maiores bancos do Brasil, priorizando um cenário de alto rigor regulatório, arquitetura Zero-Trust, trilha de auditoria completa e alto potencial de otimização FinOps (redução drástica do custo de inferência ao filtrar falsos positivos no edge).

#### Trade-offs (Consequências)
* 🟢 **Ganhos (Prós):** Máximo valor de negócio para instituições financeiras reguladas; demonstração de arquitetura robusta de compliance (LGPD/BACEN/COAF); redução estimada de até 65% nos falsos positivos encaminhados a analistas sêniores.
* 🔴 **Perdas/Riscos (Contras):** Exige rigor absoluto no manuseio de dados financeiros (Sigilo Bancário - LC 105/2001) e precisão factual de 100% no grounding regulatório (sem alucinações).

---

### ADR-002: Orquestração Multiagente A2A e Protocolo MCP sem Vendor Lock-in
- **Data:** 2026-09-15
- **Status:** Aceito

#### Contexto e Problema
A investigação de alertas de AML requer a separação clara de responsabilidades: triagem e filtragem, recuperação contextual de normativas (RAG), raciocínio investigativo e auditoria de factualidade. Além disso, a arquitetura deve evitar dependência de provedores de nuvem específicos (*vendor lock-in*), permitindo que o sistema rode em ambiente local (custo zero) ou em plataformas multinuvem corporativas (AWS, GCP, Azure).

#### Alternativas Consideradas
* **Opção 1 (Monolito GenAI):** Agente único com prompt denso contendo todas as regras e normativas.
* **Opção 2 (Plataforma Proprietária de Cloud):** AWS Bedrock Agents / GCP Vertex AI Reasoning Engine.
* **Opção 3 (Arquitetura Aberta A2A/MCP):** Orquestração desacoplada com LangGraph, Model Context Protocol (MCP) para ferramentas de dados e LiteLLM como gateway de inferência agnóstico.

#### Decisão Selecionada
Adotou-se a **Opção 3 (Arquitetura Aberta A2A/MCP)**. Cada agente possui um papel estrito e comunica-se via protocolos abertos (princípios Agent-to-Agent). As ferramentas de consulta a bancos relacionais e vetoriais são expostas como servidores MCP. O LiteLLM abstrai a chamada de modelos (SLMs/LLMs), viabilizando execução totalmente local (Ollama com Llama 3.1/Qwen 2.5) sem custos na fase de PoC e transição transparente para APIs corporativas em produção.

#### Trade-offs (Consequências)
* 🟢 **Ganhos (Prós):** Zero lock-in de fornecedor ou nuvem; custo zero na fase de prototipagem/desenvolvimento; modularidade extrema (cada agente pode ser testado isoladamente); total alinhamento com os padrões de arquitetura promovidos pela CI&T.
* 🔴 **Perdas/Riscos (Contras):** Maior complexidade inicial na definição de esquemas de comunicação inter-agentes e gerenciamento de estado da conversação.

---

### ADR-003: Arquitetura Zero-Trust com Mascaramento de PII no Perímetro
- **Data:** 2026-09-15
- **Status:** Aceito

#### Contexto e Problema
O envio de dados pessoais identificáveis (PII) — como CPF, CNPJ, nome de clientes e números de conta bancária — para modelos de inteligência artificial viola a LGPD, a Lei Complementar 105/2001 (Sigilo Bancário) e as normas de governança dos bancos. A solução deve garantir que nenhum dado sensível saia do perímetro de segurança autorizado em nenhum momento.

#### Alternativas Consideradas
* **Opção 1:** Confiar nos acordos de privacidade e APIs privadas de provedores LLM Cloud (sem mascaramento local).
* **Opção 2:** Mascaramento Sintético Local no Edge (Sanitizador PII com Regex + Microsoft Presidio) antes de qualquer inferência ou vetorização.
* **Opção 3:** Criptografia homomórfica aplicada a embeddings.

#### Decisão Selecionada
Adotou-se a **Opção 2 (Mascaramento Sintético Local no Edge)**. Antes de qualquer dado ser repassado ao pipeline multiagente ou motor RAG, um agente especializado de sanitização local substitui PIIs reais por tokens sintéticos auditáveis (ex: `CPF_01`, `CONTA_883`). O mapa de reversão é mantido estritamente em memória local cifrada e acessível apenas na renderização final da interface para o analista humano autorizado.

#### Trade-offs (Consequências)
* 🟢 **Ganhos (Prós):** Conformidade total de privacidade e Zero-Trust; garantia de que nenhum dado sensível atinja LLMs externos; execução 100% local com custo zero.
* 🔴 **Perdas/Riscos (Contras):** Necessidade de manutenção e validação rigorosa das regras de Regex e entidade de mascaramento para evitar escapes (*leaks*) não tratados.

---

### ADR-004: Estratégia FinOps e Economia de Tokens via Triagem Híbrida e Cache Semântico
- **Data:** 2026-09-15
- **Status:** Aceito

#### Contexto e Problema
A execução de pipelines RAG e inferências de LLM em grande volume de alertas de transações pode gerar custos expressivos de computação/tokens e latências elevadas. Para garantir viabilidade financeira de escala (FinOps) e operação ágil, o sistema precisa minimizar o consumo de tokens sem perda de precisão investigativa.

#### Alternativas Consideradas
* **Opção 1:** Processamento direto de 100% dos alertas por LLMs de alta capacidade.
* **Opção 2:** Pipeline Hierárquico de 3 Camadas: (1) Filtro Heurístico Determinístico $\rightarrow$ (2) Cache Semântico de Normas e Decisões Anteriores $\rightarrow$ (3) Inferência Agêntica Enxuta (RAG focalizado + SLMs/LLMs com prompts concisos).

#### Decisão Selecionada
Adotou-se a **Opção 2 (Pipeline Hierárquico de 3 Camadas)**. Regras determinísticas descatam inconsistências simples sem chamar IA. O cache semântico baseado em embeddings locais responde a consultas normativas repetitivas. Apenas alertas complexos e atípicos acionam a orquestração multiagente, utilizando prompts estritamente estruturados e janelas de contexto otimizadas.

#### Trade-offs (Consequências)
* 🟢 **Ganhos (Prós):** Redução estimada de $> 70\%$ no consumo de tokens e custo de inferência; latência drasticamente reduzida para alertas comuns; viabilidade econômica demonstrável para transição de PoC para capacidade escalável.
* 🔴 **Perdas/Riscos (Contras):** Exige afinação prévia e manutenção constante das regras de triagem heurística e validação da taxa de acerto do cache semântico.

---

### ADR-005: Estratégia de Dados: Corpus Normativo Público e Transações Sintéticas
- **Data:** 2026-09-15
- **Status:** Aceito

#### Contexto e Problema
A PoC precisa de três tipos de dados: (1) transações com alertas rotulados por tipologia, para medir o recall de tipologias críticas e a redução de falsos positivos definidos no `INTENT.md`; (2) um corpus normativo oficial para o RAG com grounding verificável; (3) listas de restrição (PEP, empresas sancionadas) para enriquecer a investigação. Transações bancárias reais de clientes brasileiros não são públicas (Sigilo Bancário - LC 105/2001), e os guardrails do projeto proíbem dados reais de clientes em qualquer etapa da PoC.

#### Alternativas Consideradas
* **Opção 1 (Somente dados públicos reais):** Inviável: não existe base pública de transações bancárias brasileiras rotuladas com tipologias de lavagem.
* **Opção 2 (100% sintético gerado do zero):** Controle total do formato, mas tipologias sem validação externa e alto esforço de modelagem antes de validar o protótipo.
* **Opção 3 (Híbrida):** Corpus normativo público oficial + benchmark sintético acadêmico rotulado como base transacional + camada sintética de adaptação ao contexto brasileiro.

#### Decisão Selecionada
Adotou-se a **Opção 3 (Híbrida)**:
* **Corpus normativo:** textos oficiais baixados das fontes primárias (BCB e COAF), começando por Circular BCB 3.978/2020 e Carta Circular BCB 4.001/2020. Cada documento é armazenado com URL de origem e hash de conteúdo, permitindo citação verificável.
* **Base transacional rotulada:** SAML-D (28 tipologias, 11 normais e 17 suspeitas; licença CC BY-NC-SA 4.0). Um mapeamento versionado relaciona cada tipologia do SAML-D às situações da Carta Circular 4.001/2020; o golden set de tipologias críticas é um subconjunto estratificado dessa base.
* **Camada brasileira sintética:** conversão para Real (BRL), inclusão de PIX como meio de pagamento e geração de CPF/CNPJ/contas sintéticos com dígitos verificadores válidos, para exercitar o mascaramento de PII (ADR-003) com formatos reais.
* **Listas de restrição:** apenas o dicionário de dados das listas oficiais (PEP, CEIS, CNEP do Portal da Transparência) é reutilizado; o conteúdo é sintético, pois as listas reais contêm dados pessoais.
* **Teste de escala FinOps:** IBM AML (AMLworld) fica reservado para testes de volume 10x/100x do custo de inferência (ADR-004), fora do golden set.

#### Trade-offs (Consequências)
* 🟢 **Ganhos (Prós):** Custo zero de aquisição de dados; recall medido contra ground truth externo e publicado; grounding ancorado em texto normativo oficial; nenhum dado pessoal real no pipeline (Zero-Trust preservado); benchmark de escala disponível para a estimativa FinOps.
* 🔴 **Perdas/Riscos (Contras):** SAML-D não reflete o contexto brasileiro, o que exige camada de adaptação e mapeamento de tipologias sujeito a viés; a licença não comercial (NC) impede reuso comercial direto, e em produção a base deve ser substituída por dados reais mascarados da instituição; os KPIs de −65% de falsos positivos e 3x de velocidade são medidos contra uma linha de base simulada, não contra a operação real.

---

### ADR-006: Fronteira entre Agentes LLM e Código Determinístico
- **Data:** 2026-09-15
- **Status:** Aceito

#### Contexto e Problema
O `INTENT.md` exige 0 citações não verificadas no dossiê, recall de 100% em tipologias críticas e latência < 20 s em hardware CPU-only. Cada nó que usa LLM adiciona latência, custo, não determinismo e risco de alucinação. É preciso decidir quais etapas do fluxo justificam orquestração agêntica e quais devem ser pipeline determinístico.

#### Alternativas Consideradas
* **Opção 1 (Tudo agêntico):** triagem, investigação, pesquisa normativa, revisão e redação do dossiê executadas por agentes LLM.
* **Opção 2 (Tudo determinístico):** regras e templates, sem LLM.
* **Opção 3 (Híbrida com fronteira explícita):** LLM apenas onde há julgamento (síntese investigativa e seleção de trechos normativos); triagem, recuperação, verificação de citação, montagem do dossiê, controle de prazo e auditoria como código determinístico.

#### Decisão Selecionada
Adotou-se a **Opção 3**. Apenas dois nós usam LLM: Investigação e Seleção de chunks. O Revisor verifica citações por hash do trecho normalizado contra o corpus, sem LLM. O dossiê é montado por template a partir de saídas JSON estruturadas; os únicos textos gerados por IA (`rationale`, `applicability`) são marcados como tal.

#### Trade-offs (Consequências)
* 🟢 **Ganhos (Prós):** grounding final garantido por construção; latência e custo concentrados em dois nós; comportamento reprodutível e testável nas etapas regulatoriamente sensíveis; resposta objetiva à pergunta "quando usar agentes vs. pipeline determinístico".
* 🔴 **Perdas/Riscos (Contras):** dossiês com redação menos fluida; o Revisor por hash rejeita citações corretas com diferença de formatação, exigindo normalização rigorosa; regras e templates precisam de manutenção.

---

### ADR-007: API REST, UI do Analista e Autenticação da PoC
- **Data:** 2026-09-15
- **Status:** Aceito

#### Contexto e Problema
O `INTENT.md` exige que dados reais do cliente apareçam apenas na tela do analista autorizado e que o aceite do Compliance Officer seja digital. A PoC precisa de contratos de integração que sobrevivam à evolução para produção, sem construir um frontend completo antes de validar o protótipo.

#### Alternativas Consideradas
* **Opção 1 (CLI/lote):** entrada e saída por arquivos, sem API.
* **Opção 2 (API REST + SPA):** FastAPI com frontend React.
* **Opção 3 (API REST + UI mínima):** FastAPI com OpenAPI e Streamlit consumindo apenas a API; RBAC por token estático por papel (`analista`, `compliance_officer`, `sistema`) lido de variável de ambiente.

#### Decisão Selecionada
Adotou-se a **Opção 3**. A API é o contrato estável (integração com sistemas corporativos no futuro); a UI Streamlit é descartável e nunca acessa bancos ou o Vault diretamente. A reidentificação só ocorre via endpoint autorizado, com `Cache-Control: no-store` e evento de auditoria.

#### Trade-offs (Consequências)
* 🟢 **Ganhos (Prós):** demonstra o fluxo ponta a ponta com Zero-Trust visível; contratos OpenAPI prontos para handoff; superfície testável por DAST (OWASP ZAP).
* 🔴 **Perdas/Riscos (Contras):** tokens estáticos não servem para produção (substituição por OIDC/SSO corporativo); Streamlit limita controle fino de sessão e UX.

---

### ADR-008: Persistência em SQLite e Trilha de Auditoria com Hash-Chain
- **Data:** 2026-09-15
- **Status:** Aceito

#### Contexto e Problema
Toda decisão (triagem, investigação, revisão, submissão, aceite) precisa ficar registrada de forma imutável e verificável, e o estado do grafo precisa sobreviver a falhas. A PoC deve rodar localmente com custo zero.

#### Alternativas Consideradas
* **Opção 1:** PostgreSQL local com tabelas append-only.
* **Opção 2:** Ledger externo ou blockchain permissionada.
* **Opção 3:** SQLite (WAL) para estado, checkpoints LangGraph e auditoria, com hash-chain SHA-256 por evento e triggers que abortam `UPDATE`/`DELETE` na tabela de auditoria.

#### Decisão Selecionada
Adotou-se a **Opção 3**. Cada evento guarda `prev_hash` e `hash = SHA-256(prev_hash ‖ JSON canônico do evento)`. Um endpoint recalcula a cadeia e aponta o primeiro evento inválido. O evento registra versões de regras, corpus, mapeamento, prompt e modelo, além do hash do prompt (nunca o conteúdo).

#### Trade-offs (Consequências)
* 🟢 **Ganhos (Prós):** zero infraestrutura; adulteração detectável; checkpoint e auditoria na mesma tecnologia; migração direta para Postgres por ser SQL.
* 🔴 **Perdas/Riscos (Contras):** hash-chain detecta mas não impede reescrita completa do arquivo (em produção exige âncora externa periódica ou armazenamento WORM); SQLite não suporta escrita concorrente em escala.

---

### ADR-009: Stack de RAG Local e Escopo do Cache Semântico
- **Data:** 2026-09-15
- **Status:** Aceito

#### Contexto e Problema
O corpus normativo é em português e a citação precisa ser exata. O ADR-004 já decidiu usar cache semântico; falta decidir a stack de embeddings e vetores e delimitar o que o cache pode armazenar sem contaminar decisões nem a avaliação.

#### Alternativas Consideradas
* **Opção 1:** embeddings via API de provedor de nuvem e base vetorial gerenciada.
* **Opção 2:** FastEmbed com modelo apenas em inglês (BGE-small) e ChromaDB.
* **Opção 3:** FastEmbed com modelo multilíngue (candidatos `paraphrase-multilingual-MiniLM-L12-v2` e `multilingual-e5-small`, escolha por recall@5 no corpus) e ChromaDB persistente local; chunking por dispositivo normativo; cache restrito a consultas normativas.

#### Decisão Selecionada
Adotou-se a **Opção 3**. O cache mapeia consulta sanitizada → `chunk_id`s, com chave que inclui `corpus_version` e invalidação total na troca de versão. O cache MUST NOT armazenar decisões, recomendações ou evidências de alertas, e fica desligado nas medições de recall e grounding do golden set.

#### Trade-offs (Consequências)
* 🟢 **Ganhos (Prós):** custo zero; nenhum dado sai da máquina; recuperação adequada ao português; cache incapaz de propagar decisão errada entre alertas.
* 🔴 **Perdas/Riscos (Contras):** modelos pequenos multilíngues têm recall menor que modelos grandes; menor taxa de acerto do cache ao limitar seu escopo; ChromaDB local não é a base de produção.

---

### ADR-010: Estratégia de Modelos SLM-First com Saída Estruturada via LiteLLM
- **Data:** 2026-09-15
- **Status:** Aceito

#### Contexto e Problema
O hardware de referência (Intel Core i7-1255U, 15,7 GB RAM, sem GPU dedicada) executa inferência apenas em CPU. Três chamadas sequenciais a modelos de 7–8B não cabem na meta de p95 < 20 s. A escolha de modelo não pode amarrar a arquitetura a um fornecedor.

#### Alternativas Consideradas
* **Opção 1:** modelo único de 7–8B (Llama 3.1 8B / Qwen 2.5 7B) em todos os nós.
* **Opção 2:** API de modelo de nuvem desde a PoC.
* **Opção 3:** SLMs primeiro (~3B para investigação, ~1,5B para seleção de trechos, quantizados Q4 via Ollama), saída JSON validada por schema, contexto limitado por nó e roteamento/fallback configurados no LiteLLM; o nome do modelo é configuração, não código.

#### Decisão Selecionada
Adotou-se a **Opção 3**. O fallback vai para modelo menor e depois para a fila humana, nunca para modelo maior. Antes do `PLAN.md`, um benchmark de tokens/s no hardware de referência valida o orçamento de latência do `SPEC.md`.

#### Trade-offs (Consequências)
* 🟢 **Ganhos (Prós):** latência viável em CPU; custo zero local; troca de provedor apenas por configuração; saídas estruturadas facilitam validação determinística.
* 🔴 **Perdas/Riscos (Contras):** SLMs raciocinam pior em casos complexos, o que aumenta encaminhamentos a `NEEDS_HUMAN`; dependência de qualidade da saída JSON em modelos pequenos.

---

### ADR-011: Recuperação de Falhas com Máquina de Estados e Checkpoint
- **Data:** 2026-09-15
- **Status:** Aceito

#### Contexto e Problema
Falhas de modelo, de servidor MCP ou do processo não podem resultar em alerta perdido, duplicado ou arquivado. Perder um alerta de tipologia crítica viola a meta de recall e expõe a instituição a descumprimento de prazo.

#### Alternativas Consideradas
* **Opção 1:** reprocessar o alerta inteiro do início em caso de erro.
* **Opção 2:** retries ilimitados até sucesso.
* **Opção 3:** máquina de estados explícita com transições validadas, checkpoint LangGraph após cada nó, retomada idempotente, no máximo 2 retries por nó, orçamento de tokens e tempo por alerta e estado terminal de segurança `NEEDS_HUMAN`.

#### Decisão Selecionada
Adotou-se a **Opção 3**. Qualquer falha, orçamento esgotado ou sanitização ambígua leva o alerta a `NEEDS_HUMAN`, preservando o que já foi produzido e o motivo. Eventos de auditoria usam chave de idempotência (`alert_id + nó + tentativa`).

#### Trade-offs (Consequências)
* 🟢 **Ganhos (Prós):** degradação segura (falha vira trabalho humano, nunca arquivamento); retomada sem custo repetido de inferência; comportamento testável por injeção de falha.
* 🔴 **Perdas/Riscos (Contras):** mais estados e transições para manter; picos de falha aumentam a fila humana.

---

### ADR-012: Gestão de Chaves, Reidentificação e Observabilidade sem PII
- **Data:** 2026-09-15
- **Status:** Aceito

#### Contexto e Problema
O ADR-003 define que o mapa de reversão fica em memória local cifrada. Falta decidir como a chave é gerida, o que acontece quando o processo reinicia (a UI perderia a reidentificação) e como observar o sistema sem que logs vazem dados pessoais.

#### Alternativas Consideradas
* **Opção 1:** persistir o mapa cifrado em disco com chave em arquivo de configuração.
* **Opção 2:** chave efêmera sem recuperação (reinício perde a reidentificação definitivamente).
* **Opção 3:** mapa cifrado com AES-GCM apenas em memória, chave obtida por interface `KeyProvider` (implementação local na PoC, KMS em produção), tokens determinísticos por ordem de aparição no alerta para reconstruir o mapa a partir do sistema de origem; logs estruturados apenas com identificadores e hashes.

#### Decisão Selecionada
Adotou-se a **Opção 3**. Se o Vault não estiver disponível, a API responde `410` e o mapa é reconstruído reprocessando a sanitização a partir do sistema de origem. Nenhum log, prompt capturado, coleção vetorial ou cache pode conter valor real, verificado por teste canário.

#### Trade-offs (Consequências)
* 🟢 **Ganhos (Prós):** nenhum dado pessoal em repouso fora do sistema de origem; caminho direto para KMS sem reescrita; observabilidade auditável sem risco LGPD.
* 🔴 **Perdas/Riscos (Contras):** reconstrução depende de acesso ao sistema de origem; depuração mais difícil sem payloads nos logs.
