# CLAUDE.md — Agentic AML & Regulatory Compliance Guardian

## Contexto do projeto
Agente de IA que irá monitorar transações financeiras e identificar padrões suspeitos de lavagem de dinheiro e financiamento ao terrorismo, de acordo com as normas do Banco Central do Brasil e COAF.

## O que o Modelo NÃO faz
Não bloqueia saldos bancários nem trava operações em tempo real de forma unilateral.
Não transmite dossiês diretamente ao COAF sem o aceite digital do Compliance Officer.
Não envia dados bancários não anonimizados para provedores externos de LLM.

## Stack
- Python 3.11+ · LangGraph (orquestração multiagente) · MCP (ferramentas de dados) · LiteLLM (gateway de inferência)
- SLMs/LLMs locais via Ollama (Llama 3.1 / Qwen 2.5) — PoC com custo zero; cloud via LiteLLM em produção
- Sanitização PII: Regex + Microsoft Presidio · Cache semântico local · Testes: pytest

## Guardrails Arquiteturais
1. **Zero-Trust:** NENHUM PII real (CPF/CNPJ/conta/nome) pode chegar a LLM, RAG ou log. Sanitização obrigatória antes de qualquer inferência/vetorização. Mapa de reversão só em memória local cifrada, renderizado apenas na UI do analista.
2. **FinOps:** Pipeline hierárquico obrigatório: Regras heurísticas determinísticas → Cache semântico → Inferência agêntica (só alertas complexos). Nunca envie 100% dos alertas a LLM.
3. **Sem lock-in:** Toda chamada de modelo via LiteLLM; toda ferramenta de dados via MCP. Nunca importar SDKs proprietários de cloud diretamente.
4. **Factualidade:** Respostas regulatórias exigem grounding citado (RAG). Proibido alucinar norma, número de circular ou artigo.

## Economia Máxima de Tokens (aplicar sempre)
- **Busca cirúrgica:** `Grep`/`Glob` com limites; nunca ler arquivo inteiro para achar um símbolo.
- **Edição atômica:** `Edit` pontual; nunca reescrever arquivo inteiro.
- **Delegar exploração** ampla (docs densos, logs longos, análise de codebase) a subagentes — receber só o resumo.
- **Escopo por paths:** regras de módulo em `.claude/rules/*.md` (com `paths:`); rotinas multi-etapas em `.claude/skills/<nome>/SKILL.md`.
- **Hooks, não LLM:** formatar/lintar via hooks (PostToolUse), custo zero de token.
- **Reusar contexto:** não recolar texto já presente na conversa; referenciar por `arquivo:linha`.
- **Testes focados:** rodar apenas o teste afetado (`pytest -k`), não a suite inteira.
- **Flags não-interativas:** `--yes`, `--quiet`, `--no-pager`. Nunca rodar comando que espere input.
- **Fail-fast:** checar exit code + stderr antes de prosseguir.

## Workflow
- **Simples** (1-2 arquivos, escopo claro): executar direto → teste focado.
- **Complexo** (múltiplos módulos/arquitetura): Plan Mode → validar plano → executar em lotes.

## ADR — Regras de Atualização
- Toda decisão estrutural (lib, banco, padrão, contrato, infra, FinOps) vira entrada nova em `docs/ADR.md`.
- Histórico cumulativo (nunca apagar); numeração sequencial (ADR-00N); manter índice do topo atualizado; seguir exatamente a estrutura existente.

## Segurança e Estabilidade (inviolável)
- NUNCA ler/imprimir/criar/alterar `.env`, chaves ou tokens no chat.
- NUNCA remover comentários, docstrings ou código funcional não relacionado à tarefa.
- Sem `rm -rf`, `git reset --hard`, `drop` sem confirmação explícita.
- Sem placeholders/`TODO`: código entregue é sempre funcional.
- Dados de teste: apenas sintéticos; nunca dados reais de clientes em fixtures ou exemplos.

## Formato de Resposta
- Sem preâmbulos ou repetição do pedido. Ação/diff/resultado direto.
- Ao concluir: (1) o que mudou (arquivos), (2) comandos de validação + resultado, (3) próximo passo se houver.
