# Intent: Reduzir o esforço manual e o risco regulatório na investigação de alertas PLD/FT

## Autor
marcosjcn94@gmail.com — dono do problema e responsável pelo gate deste documento.

## Visão do produto
Uma plataforma que investiga alertas de transações atípicas no lugar do analista, entrega uma minuta
de dossiê fundamentada nas normas do BACEN e do COAF e deixa a decisão final sempre com um humano
autorizado.

## Problema
- Sistemas legados de monitoramento geram dezenas de milhares de alertas de PLD/FT por dia; entre 90% e 95% são falsos positivos.
- Analistas de compliance gastam horas montando dossiês manuais até para descartar alertas simples.
- A fila acumulada aumenta o risco de a instituição perder o prazo de comunicação ao COAF e ser autuada.
- Cada investigação precisa ser rastreável e fundamentada em norma real; uma citação normativa errada invalida o dossiê.

## Quem é afetado
- **Analista de compliance:** investiga alertas e redige dossiês; hoje é o gargalo.
- **Compliance Officer:** aprova ou rejeita a comunicação ao COAF; responde pela instituição.
- **Instituição financeira regulada:** exposta a multas, sigilo bancário (LC 105/2001) e LGPD.

## Resultado esperado (KPIs de negócio)
| KPI | Meta | Como é verificado |
| :--- | :--- | :--- |
| Falsos positivos encaminhados à equipe sênior | −65% | Comparação com a taxa de encaminhamento de referência no mesmo conjunto de alertas |
| Velocidade de investigação e montagem de dossiê | 3x mais rápida | Tempo médio por dossiê comparado com o processo manual de referência |
| Autuações por perda de prazo BACEN/COAF | Zero (objetivo de negócio) | Proxy na PoC: 100% dos dossiês gerados dentro do prazo interno derivado da Circ. 3.978/2020 |

## Critérios de sucesso verificáveis
- **Recall de tipologias críticas:** 100% sobre um golden set sintético rotulado; nenhum alerta de tipologia crítica é arquivado automaticamente.
- **Grounding normativo:** o dossiê entregue ao analista contém 0 citações não verificadas. A saída bruta da etapa de pesquisa normativa, antes da revisão, deve ter ≥ 99% de citações exatas.
- **Latência:** < 20 segundos por minuta de dossiê.
- **Custo:** < R$ 0,005 por alerta investigado (zero em execução local).
- **Privacidade:** 0 ocorrências de dado pessoal real (CPF, CNPJ, conta, nome) fora do perímetro autorizado, em modelos, bases de conhecimento ou logs.

## Como é "pronto" para o usuário
Dado um alerta, o analista recebe em menos de 20 segundos uma minuta de dossiê que (a) aponta a
tipologia de lavagem suspeita ou recomenda arquivamento justificado, (b) cita cada norma usada com
referência verificável, (c) exibe os dados reais do cliente apenas na sua tela autorizada e
(d) fica registrada numa trilha de auditoria que não pode ser alterada.

## Primeira fatia vertical (PoC)
Um alerta sintético entra, passa pela triagem, é investigado e sai como minuta de dossiê revisada e
auditada, pronta para aceite do Compliance Officer. Processamento em lote, integrações reais e
escala ficam para depois da validação desta fatia.

## Fora de escopo
- Bloquear saldos ou travar operações em tempo real de forma unilateral.
- Transmitir dossiês ao COAF sem o aceite digital do Compliance Officer.
- Enviar dados bancários não anonimizados a provedores externos de modelos de IA.
- Usar dados reais de clientes na PoC (apenas dados sintéticos).
- Substituir a decisão humana de comunicar ou arquivar.

## Restrições
- **Regulatórias:** Circular BCB 3.978/2020, normas do COAF, LGPD e LC 105/2001.
- **Privacidade (ADR-003):** nenhum dado pessoal real chega a modelos, bases de conhecimento ou logs; a reidentificação só acontece na interface do analista autorizado.
- **Custo (ADR-004):** nem todo alerta pode passar por IA; alertas simples são resolvidos por regras determinísticas, e consultas repetidas reaproveitam respostas anteriores antes de acionar inferência.
- **Independência de fornecedor (ADR-002):** a solução deve rodar localmente com custo zero na PoC e migrar para qualquer nuvem corporativa sem reescrita.
- **Factualidade:** nenhuma norma, circular ou artigo pode ser citado sem fonte recuperada e verificada.
- **Auditabilidade:** toda decisão (triagem, investigação, revisão, aceite) fica registrada de forma imutável.

## Terminologia
- **Alerta:** transação ou conjunto de transações sinalizado como atípico pelo monitoramento.
- **Tipologia:** padrão de lavagem de dinheiro ou financiamento ao terrorismo reconhecido pela regulação.
- **Dossiê:** minuta de Comunicação de Operação Suspeita ou de arquivamento justificado, gerada para revisão humana.
- **Token sintético:** substituto auditável de um dado pessoal real (ex: `CPF_01`).
- **Aceite:** aprovação digital do Compliance Officer, obrigatória antes de qualquer comunicação ao COAF.

## Perguntas abertas
- Quais são os prazos exatos de análise e de comunicação ao COAF pela Circ. 3.978/2020? (confirmar em fonte oficial do BCB antes do SPEC)
- Quais tipologias compõem o conjunto "crítico" do golden set, e qual norma oficial as lista?
- A meta de redução > 70% de tokens (ADR-004) é atingível combinando o descarte determinístico (~40%) com a taxa de acerto do reaproveitamento de respostas?
- Qual é o processo manual de referência (tempo por dossiê, taxa de encaminhamento) usado para medir os KPIs de −65% e 3x?
- Em qual hardware de referência a latência < 20 s é medida na execução local?
- A interface do analista faz parte da PoC ou basta uma saída revisável fora de tela?

## Gate
Status: aprovado pelo autor em 2026-09-15. `SPEC.md` herda estas restrições e perguntas abertas como ponto de partida.
