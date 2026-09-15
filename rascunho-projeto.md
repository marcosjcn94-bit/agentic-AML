# Plataforma Autônoma de Investigação de Alertas e Compliance AML/BACEN (Agentic AML & Regulatory Compliance Guardian)
Alinhamento com exigências estritas do BACEN (Circ. 3.978) e COAF.

## Problema que será resolvido:
Sistemas legados de monitoramento geram dezenas de milhares de alertas diários de PLD/FT (Prevenção à Lavagem de Dinheiro), dos quais 90% a 95% são falsos positivos. Analistas de compliance gastam horas preenchendo dossiês manuais para descartar alertas simples, gerando risco de multas por intempestividade de comunicação ao COAF.

## Definição de KPI de negócio:
Redução de 65% nos falsos positivos encaminhados para a equipe sênior.
Aumento de 3x na velocidade de investigação e montagem de Dossiê de Comunicação de Operação Suspeita.
Zero autuações regulatórias por estouro de prazo do BACEN/COAF.

## Objetivo do modelo:
Ingerir alertas transacionais atípicos, cruzar dados históricos de movimentação do cliente mascarado, consultar via RAG as circulares normativas do BACEN/COAF e produzir uma minuta de relatório de conformidade apontando tipologias de lavagem ou recomendando arquivamento justificado.

## O que o modelo NÃO faz:
Não bloqueia saldos bancários nem trava operações em tempo real de forma unilateral.
Não transmite dossiês diretamente ao COAF sem o aceite digital do Compliance Officer.
Não envia dados bancários não anonimizados para provedores externos de LLM.

## Métricas de avaliação:
Recall na identificação de tipologias regulatórias críticas de AML: $100%$.
Grounding de Citação Normativa (percentual de citações exatas de resoluções sem alucinação) $\ge 99%$.
Latência por dossiê pré-formatado: $< 20$ segundos.
Custo de inferência por alerta investigado: $< \text{R$} 0,005$ (ou zero localmente).

## Resumo da arquitetura:
Fila de Alertas (Mock Kafka/SQLite) $\rightarrow$ Filtro de Heurística Determinística (descarta 40% sem LLM) $\rightarrow$ Edge PII Masker $\rightarrow$ Agente Investigador A2A (MCP tool consultando histórico relacional) $\rightarrow$ Agente RAG Normativo (base vetorial com normas BACEN) $\rightarrow$ Agente Revisor Regulatório $\rightarrow$ Log imutável com hash criptográfico de cada decisão tomada.

## Ferramentas (Custo Zero):
Python, LiteLLM, ChromaDB/SQLite, FastEmbed (BGE-small local), Guardrails AI / Presidio, LangGraph, pytest.