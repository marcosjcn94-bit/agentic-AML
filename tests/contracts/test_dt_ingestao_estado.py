"""Contrato de registro de estado do alerta (DT-05; SPEC.md §8.2, RF-09, RF-10; T0.2)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from aml_guardian.contracts.ingestion import AlertRecord, AlertState, TriageLevel

ALERT_ID = "8f5c2a1e-3b7d-4c9a-9e21-6a0f4d2b7c11"


# DT-05 -----------------------------------------------------------------------


def _record(**overrides: object) -> dict[str, Any]:
    record: dict[str, Any] = {
        "alert_id": ALERT_ID,
        "state": "RECEIVED",
        "triage_level": None,
        "selected_at": "2026-09-15T13:00:00Z",
        "prazo_interno": None,
        "prazo_regulatorio_analise": None,
        "failure_reason": None,
        "created_at": "2026-09-15T13:00:01Z",
        "updated_at": "2026-09-15T13:00:01Z",
    }
    record.update(overrides)
    return record


def test_dt_ingestao_estados_do_rf10() -> None:
    assert {s.value for s in AlertState} == {
        "RECEIVED",
        "SANITIZED",
        "TRIAGED",
        "INVESTIGATING",
        "RESEARCHING",
        "REVIEWING",
        "DRAFT_READY",
        "SUBMITTED",
        "APPROVED",
        "RETURNED",
        "NEEDS_HUMAN",
    }
    assert {t.value for t in TriageLevel} == {"PROPOR_ARQUIVAMENTO", "INVESTIGAR"}


def test_dt_ingestao_registro_valido() -> None:
    record = AlertRecord.model_validate(
        _record(
            state="TRIAGED",
            triage_level="INVESTIGAR",
            prazo_interno="2026-09-20T13:00:00Z",
            prazo_regulatorio_analise="2026-10-30T13:00:00Z",
        )
    )
    assert record.state is AlertState.TRIAGED
    assert record.triage_level is TriageLevel.INVESTIGAR


@pytest.mark.parametrize(
    "overrides",
    [
        {"state": "PROPOR_ARQUIVAMENTO"},
        {"triage_level": "ARQUIVAR"},
        {"state": "NEEDS_HUMAN"},
        {"state": "NEEDS_HUMAN", "failure_reason": ""},
        {"created_at": "2026-09-15T13:00:01"},
    ],
)
def test_dt_ingestao_registro_invalido(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        AlertRecord.model_validate(_record(**overrides))


def test_dt_ingestao_needs_human_preserva_motivo() -> None:
    record = AlertRecord.model_validate(_record(state="NEEDS_HUMAN", failure_reason="SANITIZER_AMBIGUOUS"))
    assert record.failure_reason == "SANITIZER_AMBIGUOUS"


@pytest.mark.parametrize(
    ("state", "triage_level"),
    [
        ("RECEIVED", "INVESTIGAR"),
        ("SANITIZED", "PROPOR_ARQUIVAMENTO"),
        ("TRIAGED", None),
        ("DRAFT_READY", None),
        ("SUBMITTED", None),
        ("APPROVED", None),
        ("RETURNED", None),
        ("INVESTIGATING", "PROPOR_ARQUIVAMENTO"),
        ("RESEARCHING", None),
        ("REVIEWING", "PROPOR_ARQUIVAMENTO"),
    ],
)
def test_dt_ingestao_registro_nivel_incoerente_com_estado(state: str, triage_level: str | None) -> None:
    with pytest.raises(ValidationError):
        AlertRecord.model_validate(_record(state=state, triage_level=triage_level))


@pytest.mark.parametrize(
    ("state", "triage_level"),
    [
        ("RECEIVED", None),
        ("SANITIZED", None),
        ("TRIAGED", "PROPOR_ARQUIVAMENTO"),
        ("DRAFT_READY", "PROPOR_ARQUIVAMENTO"),
        ("APPROVED", "INVESTIGAR"),
        ("REVIEWING", "INVESTIGAR"),
        ("NEEDS_HUMAN", None),
        ("NEEDS_HUMAN", "INVESTIGAR"),
    ],
)
def test_dt_ingestao_registro_nivel_coerente_com_estado(state: str, triage_level: str | None) -> None:
    reason = "FALHA_SINTETICA" if state == "NEEDS_HUMAN" else None
    record = AlertRecord.model_validate(_record(state=state, triage_level=triage_level, failure_reason=reason))
    assert record.state.value == state
