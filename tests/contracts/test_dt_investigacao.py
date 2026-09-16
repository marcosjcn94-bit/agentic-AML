"""Contratos de triagem e investigação (DT-06, DT-07, DT-16; SPEC.md §8.2, RF-03, RF-05; T0.3).

DT-08 a DT-11 em test_dt_investigacao_dossie.py. Dados sintéticos; contas só como token (`CONTA_02`).
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from pydantic import ValidationError

from aml_guardian.contracts.pipeline import (
    InvestigationFeatures,
    InvestigationOutput,
    Recommendation,
    TriageDecision,
    Typology,
    missing_evidence_ids,
)

ALERT_ID = "8f5c2a1e-3b7d-4c9a-9e21-6a0f4d2b7c11"

TRIAGE: dict[str, Any] = {
    "alert_id": ALERT_ID,
    "level": "INVESTIGAR",
    "fired_rules": [{"rule_id": "RF03-FRAG", "description": "Fragmentação de depósitos em espécie", "critical": True}],
    "rules_version": 1,
}

FEATURES: dict[str, Any] = {
    "alert_id": ALERT_ID,
    "features_version": 1,
    "features": [
        {"feature_id": "F01", "name": "tx_janela", "value": 12, "transaction_ids": ["tx-0001", "tx-0002"]},
        {"feature_id": "F03", "name": "abaixo_limiar", "value": 9, "transaction_ids": ["tx-0001"]},
        {"feature_id": "F11", "name": "vol_vs_media180d", "value": "4.2x", "transaction_ids": []},
        {"feature_id": "F14", "name": "CONTA_02", "value": "in=3 out=0 brl=29400", "transaction_ids": ["tx-0002"]},
    ],
}

INVESTIGATION: dict[str, Any] = {
    "typology_hypothesis": "Structuring",
    "confidence": 0.82,
    "recommendation": "COMUNICAR",
    "evidence_feature_ids": ["F03", "F01"],
}

# Enum de geração do AGENTS.md §4.2 (17 rótulos suspeitos do SAML-D + NENHUMA).
AGENTS_TYPOLOGY_ENUM = [
    "Fan-Out", "Fan-In", "Cycle", "Bipartite", "Stacked Bipartite", "Scatter-Gather", "Gather-Scatter",
    "Layered Fan-In", "Layered Fan-Out", "Structuring", "Smurfing", "Over-Invoicing", "Deposit-Send",
    "Cash Withdrawal", "Single Large Transaction", "Behavioural Change 1", "Behavioural Change 2", "NENHUMA",
]  # fmt: skip


def _copy(payload: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(payload)


# DT-06 ------------------------------------------------------------------------


def test_dt_investigacao_triagem_valida() -> None:
    decision = TriageDecision.model_validate(_copy(TRIAGE))
    assert decision.fired_rules[0].critical is True
    assert decision.rules_version == 1


@pytest.mark.parametrize("field", ["alert_id", "level", "fired_rules", "rules_version"])
def test_dt_investigacao_triagem_sem_campo_obrigatorio(field: str) -> None:
    payload = _copy(TRIAGE)
    del payload[field]
    with pytest.raises(ValidationError):
        TriageDecision.model_validate(payload)


def test_dt_investigacao_triagem_arquivamento_com_detector_critico_rejeitado() -> None:
    payload = _copy(TRIAGE)
    payload["level"] = "PROPOR_ARQUIVAMENTO"
    with pytest.raises(ValidationError, match="crítico"):
        TriageDecision.model_validate(payload)


def test_dt_investigacao_triagem_arquivamento_sem_critico_aceito() -> None:
    payload = _copy(TRIAGE)
    payload["level"] = "PROPOR_ARQUIVAMENTO"
    payload["fired_rules"][0]["critical"] = False
    assert TriageDecision.model_validate(payload).fired_rules[0].critical is False


@pytest.mark.parametrize("version", [0, "1", True])
def test_dt_investigacao_triagem_rules_version_invalida(version: object) -> None:
    payload = _copy(TRIAGE)
    payload["rules_version"] = version
    with pytest.raises(ValidationError):
        TriageDecision.model_validate(payload)


# DT-07 ------------------------------------------------------------------------


def test_dt_investigacao_saida_valida() -> None:
    output = InvestigationOutput.model_validate(_copy(INVESTIGATION))
    assert output.typology_hypothesis is Typology.STRUCTURING
    assert output.recommendation is Recommendation.COMUNICAR


def test_dt_investigacao_enum_tipologias_do_spec() -> None:
    assert [t.value for t in Typology] == AGENTS_TYPOLOGY_ENUM
    assert len(Typology) == 18


def test_dt_investigacao_enum_recomendacao_do_spec() -> None:
    assert {r.value for r in Recommendation} == {"COMUNICAR", "ARQUIVAR", "INCONCLUSIVO"}


@pytest.mark.parametrize("typology", ["Money Mule", "structuring", "NENHUM", ""])
def test_dt_investigacao_tipologia_fora_do_enum(typology: str) -> None:
    payload = _copy(INVESTIGATION)
    payload["typology_hypothesis"] = typology
    with pytest.raises(ValidationError):
        InvestigationOutput.model_validate(payload)


@pytest.mark.parametrize("confidence", [1.01, -0.01, True, float("nan"), "0.5"])
def test_dt_investigacao_confidence_invalida(confidence: object) -> None:
    payload = _copy(INVESTIGATION)
    payload["confidence"] = confidence
    with pytest.raises(ValidationError):
        InvestigationOutput.model_validate(payload)


@pytest.mark.parametrize("confidence", [0, 1, 0.0, 1.0])
def test_dt_investigacao_confidence_nos_limites(confidence: float) -> None:
    payload = _copy(INVESTIGATION)
    payload["confidence"] = confidence
    assert InvestigationOutput.model_validate(payload).confidence == confidence


def test_dt_investigacao_recomendacao_fora_do_enum() -> None:
    payload = _copy(INVESTIGATION)
    payload["recommendation"] = "DEVOLVER"
    with pytest.raises(ValidationError):
        InvestigationOutput.model_validate(payload)


def test_dt_investigacao_quatro_evidencias_rejeitadas() -> None:
    payload = _copy(INVESTIGATION)
    payload["evidence_feature_ids"] = ["F01", "F03", "F11", "F14"]
    with pytest.raises(ValidationError):
        InvestigationOutput.model_validate(payload)


def test_dt_investigacao_tres_evidencias_aceitas() -> None:
    payload = _copy(INVESTIGATION)
    payload["evidence_feature_ids"] = ["F01", "F03", "F11"]
    assert len(InvestigationOutput.model_validate(payload).evidence_feature_ids) == 3


@pytest.mark.parametrize("feature_id", [3, "3", "F3", "f03", "F03 "])
def test_dt_investigacao_evidencia_fora_do_formato(feature_id: object) -> None:
    payload = _copy(INVESTIGATION)
    payload["evidence_feature_ids"] = [feature_id]
    with pytest.raises(ValidationError):
        InvestigationOutput.model_validate(payload)


def test_dt_investigacao_chave_curta_nao_expandida_rejeitada() -> None:
    with pytest.raises(ValidationError):
        InvestigationOutput.model_validate({"t": "Structuring", "c": 0.8, "r": "COMUNICAR", "e": [3]})


# DT-16 ------------------------------------------------------------------------


def test_dt_investigacao_features_validas() -> None:
    features = InvestigationFeatures.model_validate(_copy(FEATURES))
    assert [f.feature_id for f in features.features] == ["F01", "F03", "F11", "F14"]
    assert features.features[0].value == 12
    assert features.features[2].value == "4.2x"


@pytest.mark.parametrize("field", ["alert_id", "features", "features_version"])
def test_dt_investigacao_features_sem_campo_obrigatorio(field: str) -> None:
    payload = _copy(FEATURES)
    del payload[field]
    with pytest.raises(ValidationError):
        InvestigationFeatures.model_validate(payload)


@pytest.mark.parametrize("field", ["feature_id", "name", "value", "transaction_ids"])
def test_dt_investigacao_feature_sem_campo_obrigatorio(field: str) -> None:
    payload = _copy(FEATURES)
    del payload["features"][0][field]
    with pytest.raises(ValidationError):
        InvestigationFeatures.model_validate(payload)


def test_dt_investigacao_feature_id_duplicado_rejeitado() -> None:
    payload = _copy(FEATURES)
    payload["features"][1]["feature_id"] = "F01"
    with pytest.raises(ValidationError, match="F01"):
        InvestigationFeatures.model_validate(payload)


@pytest.mark.parametrize("value", [1.5, True, "", None])
def test_dt_investigacao_feature_valor_invalido(value: object) -> None:
    payload = _copy(FEATURES)
    payload["features"][0]["value"] = value
    with pytest.raises(ValidationError):
        InvestigationFeatures.model_validate(payload)


def test_dt_investigacao_features_vazias_rejeitadas() -> None:
    payload = _copy(FEATURES)
    payload["features"] = []
    with pytest.raises(ValidationError):
        InvestigationFeatures.model_validate(payload)


# Validação cruzada DT-07 × DT-16 (RF-05) ----------------------------------------


def test_dt_investigacao_evidencias_todas_no_dt16() -> None:
    output = InvestigationOutput.model_validate(_copy(INVESTIGATION))
    features = InvestigationFeatures.model_validate(_copy(FEATURES))
    assert missing_evidence_ids(output, features) == []


def test_dt_investigacao_evidencia_inexistente_no_dt16_listada_em_ordem() -> None:
    payload = _copy(INVESTIGATION)
    payload["evidence_feature_ids"] = ["F09", "F03", "F02"]
    output = InvestigationOutput.model_validate(payload)
    features = InvestigationFeatures.model_validate(_copy(FEATURES))
    assert missing_evidence_ids(output, features) == ["F09", "F02"]
