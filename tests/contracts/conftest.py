"""Amostras sintéticas de contratos já sanitizados, compartilhadas pelos testes de envelope e estado (T0.4)."""

from __future__ import annotations

import copy
from typing import Any

import pytest

ALERT_ID = "8f5c2a1e-3b7d-4c9a-9e21-6a0f4d2b7c11"
OTHER_ALERT_ID = "11111111-2222-4333-8444-555555555555"
NORM_TEXT = "Texto normativo sintético do dispositivo usado apenas em teste."

_CITATION: dict[str, Any] = {
    "chunk_id": "chunk-0001",
    "article_ref": "Circ3978/art43/p1",
    "quoted_text": NORM_TEXT,
    "applicability": "Texto curado sintético de aplicabilidade.",
}

_SAMPLES: dict[str, Any] = {
    "sanitized_alert": {
        "alert_id": ALERT_ID,
        "source_rule_id": "LEG-ESPECIE-FRAG-01",
        "selected_at": "2026-09-15T13:00:00Z",
        "occurrence_window": {"start": "2026-09-08T00:00:00Z", "end": "2026-09-14T23:59:59Z"},
        "sender_account": "CONTA_01",
        "sender_customer": {"name": "NOME_01", "cpf_cnpj": "CPF_01"},
        "transactions": [
            {
                "transaction_id": "tx-0001",
                "timestamp": "2026-09-09T10:12:00Z",
                "amount_brl": "9800.00",
                "payment_type": "ESPECIE_DEPOSITO",
                "sender_account": "CONTA_01",
                "receiver_account": "CONTA_01",
                "sender_location": "BR",
                "receiver_location": "BR",
                "currency_sent": "BRL",
                "currency_received": "BRL",
            }
        ],
        "pii_token_count": 3,
        "sanitizer_version": "sanitizer-1",
    },
    "triage": {
        "alert_id": ALERT_ID,
        "level": "INVESTIGAR",
        "fired_rules": [{"rule_id": "R-ESPECIE-01", "description": "Espécie fragmentada sintética", "critical": True}],
        "rules_version": 1,
    },
    "features": {
        "alert_id": ALERT_ID,
        "features": [{"feature_id": "F03", "name": "abaixo_limiar", "value": 9, "transaction_ids": ["tx-0001"]}],
        "features_version": 1,
    },
    "investigation": {
        "typology_hypothesis": "Structuring",
        "confidence": 0.82,
        "recommendation": "COMUNICAR",
        "evidence_feature_ids": ["F03"],
    },
    "citation": _CITATION,
    "review": {"verified_citations": [_CITATION], "rejected_citations": [], "grounding_raw_ratio": 1.0},
    "dossier": {
        "dossier_id": "0b7e6f1a-2c3d-4e5f-8a9b-1c2d3e4f5a6b",
        "alert_id": ALERT_ID,
        "type": "COS",
        "summary": "Minuta sintética gerada por template.",
        "typology": "Structuring",
        "cc4001_incisos": ["I"],
        "evidence": [{"feature_id": "F03", "name": "abaixo_limiar", "value": 9, "transaction_ids": ["tx-0001"]}],
        "citations": [_CITATION],
        "recommendation": "COMUNICAR",
        "ai_generated_fields": ["typology_hypothesis", "confidence", "recommendation", "evidence_feature_ids"],
        "deadlines": {
            "selecao_em": "2026-09-15T13:00:00Z",
            "prazo_interno": "2026-09-20T13:00:00Z",
            "prazo_regulatorio_analise": "2026-10-30T13:00:00Z",
        },
        "versions": {"rules": 1, "corpus": "corpus-0001", "mapping": 1, "features": 1, "prompt": "v1", "model": "m"},
        "status": "DRAFT_READY",
    },
}


@pytest.fixture
def sample() -> dict[str, Any]:
    """Cópia profunda por teste: contratos sintéticos DT-04, DT-06, DT-07, DT-09, DT-10, DT-11 e DT-16."""
    return copy.deepcopy(_SAMPLES)
