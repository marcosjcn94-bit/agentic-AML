# Demonstração (5–10 minutos)

Use somente os dados sintéticos do projeto. Antes da apresentação, instale o ambiente conforme o README e
confirme que Docker e Ollama estão ativos.

1. Inicie `ollama serve`, API e Streamlit com os comandos do README (1 min).
2. Acesse `GET /health` e explique que SQLite, corpus e Ollama precisam estar saudáveis (30 s).
3. Envie um alerta sintético para `POST /alerts` com Bearer do papel `sistema`; mostre o `alert_id` e o estado
   `DRAFT_READY` ou `NEEDS_HUMAN`, sem exibir o payload bruto em logs (1 min).
4. Na UI (`http://localhost:8501`), filtre a fila por estado/risco, abra o alerta e mostre o dossiê mascarado,
   os campos marcados como gerados por IA e a citação verificada (2 min).
5. Clique em **Reidentificar**. Explique que o valor existe somente na sessão, recebe `Cache-Control: no-store`
   e gera `PII_REVEALED`; troque de alerta para demonstrar a limpeza (1 min).
6. Como analista, clique em **Submeter para decisão**. Recarregue a fila e, como officer, registre
   `COMUNICAR`, `ARQUIVAR` ou `DEVOLVER` com justificativa de ao menos 50 caracteres (1 min).
7. Consulte `/audit/{alert_id}` com Bearer do officer e mostre os eventos encadeados; use `/audit/verify` para
   confirmar a integridade (1 min).
8. Encerre com o resultado honesto: No-Go por recall crítico de 18,33%, grounding não medido e risco residual
   de dependências. A PoC demonstra os guardrails, não prontidão produtiva (30 s).

Nunca use CPF, CNPJ, nome, conta ou lista de restrição reais na demonstração.
