"""Amostra sintética para o avaliador (T1.13): payloads gerados em runtime, nunca dado real (`CLAUDE.md`).

Reaproveita o mesmo padrão de `tests/e2e/test_e2e.py` (T1.12) — detector crítico de fragmentação, que garante
`TriageLevel.INVESTIGAR` por construção — para medir o fluxo mais caro do grafo (o único nó LLM).
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from aml_guardian.config.triage import TriageRulesConfig, load_triage_rules
from aml_guardian.norms.normalize import text_sha256
from aml_guardian.sourcedata.documentos import gera_cpf

TEXTO_NORMATIVO_AMOSTRA = "Fragmentação de depósitos em espécie para dissimular o valor total da movimentação."


def payload_investigar(rules: TriageRulesConfig, seed: int) -> dict:
    """Payload cru que dispara o detector crítico de fragmentação (RF-03), sempre `INVESTIGAR`."""
    rng = random.Random(seed)
    cpf = gera_cpf(rng)
    sender = f"{rng.randrange(10**9, 10**10)}"
    receiver = f"{rng.randrange(10**9, 10**10)}"
    cfg = rules.detectores_criticos.fragmentacao
    inicio = datetime(2026, 9, 1, tzinfo=UTC)
    transacoes = [
        {
            "transaction_id": f"tx-eval-{seed:04d}-{i:04d}",
            "timestamp": (inicio + timedelta(days=i)).isoformat(),
            "amount_brl": "500.00",
            "payment_type": "PIX",
            "sender_location": "BR",
            "receiver_location": "BR",
            "currency_sent": "BRL",
            "currency_received": "BRL",
            "sender_account": sender,
            "receiver_account": receiver,
        }
        for i in range(cfg.min_transacoes)
    ]
    fim = (inicio + timedelta(days=cfg.janela_dias)).isoformat()
    return {
        "alert_id": str(uuid4()),
        "source_rule_id": "LEG-EVAL-AMOSTRA-01",
        "selected_at": inicio.isoformat(),
        "occurrence_window": {"start": inicio.isoformat(), "end": fim},
        "sender_account": sender,
        "sender_customer": {"name": "Amostra Avaliador Ltda", "cpf_cnpj": cpf},
        "transactions": transacoes,
    }


def gera_amostra(tamanho: int, rules: TriageRulesConfig | None = None) -> list[dict]:
    """`tamanho` payloads determinísticos e disjuntos (contas e `alert_id` distintos por seed)."""
    rules = rules or load_triage_rules()
    return [payload_investigar(rules, seed=1000 + i) for i in range(tamanho)]


def mcp02_sem_ocorrencia(customer_id: str, cpf_cnpj_token: str | None = None) -> dict:
    """Fake do MCP-02 (T1.3): amostra sintética nunca aparece em lista de restrição."""
    return {
        "status": "success",
        "customer_id": customer_id,
        "pep": "nao",
        "ceis": "nao",
        "cnep": "nao",
        "list_version": "v1",
    }


def mcp01_historico_vazio(customer_id: str, window_days: int) -> dict:
    """Fake do MCP-01 (T1.3): amostra sintética sem histórico de 180 dias."""
    return {"status": "success", "customer_id": customer_id, "total_amount": "0.00", "transaction_count": 0}


def norms_searcher_fixo():
    """Fake do MCP-03 (T1.7): isola a latência medida da disponibilidade do corpus normativo real."""

    def searcher(query: str, top_k: int, corpus_version: str) -> dict:
        return {
            "status": "success",
            "results": [{"chunk_id": "chunk-eval", "article_ref": "CC4001/art1/i1/d", "score": 0.95}],
        }

    return searcher


def norms_getter_fixo():
    """Fake do MCP-04 (T1.7) casado com `norms_searcher_fixo`: citação sempre verificável pelo Revisor."""
    sha = text_sha256(TEXTO_NORMATIVO_AMOSTRA)

    def getter(chunk_id: str, corpus_version: str) -> dict:
        return {"status": "success", "chunk_id": chunk_id, "text": TEXTO_NORMATIVO_AMOSTRA, "text_sha256": sha}

    return getter
