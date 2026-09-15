"""Contrato do estado do grafo persistido no checkpoint (`InvestigationState`; SPEC.md §9.3, RF-10; T0.4)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from aml_guardian.contracts.envelope import Node
from aml_guardian.contracts.runtime import InvestigationState

OTHER_ALERT_ID = "11111111-2222-4333-8444-555555555555"
TRACE_ID = "7a6b5c4d-3e2f-4a1b-9c8d-7e6f5a4b3c2d"


def _state(sample: dict[str, Any], state: str = "SANITIZED", **overrides: object) -> dict[str, Any]:
    data: dict[str, Any] = {
        "alert_id": sample["sanitized_alert"]["alert_id"],
        "trace_id": TRACE_ID,
        "state": state,
        "sanitized_alert": sample["sanitized_alert"],
        "budget": {"tokens_used": 0, "started_at": "2026-09-15T13:00:01Z"},
    }
    data.update(overrides)
    return data


def _draft_ready(sample: dict[str, Any], **overrides: object) -> dict[str, Any]:
    full = {
        "triage": sample["triage"],
        "features": sample["features"],
        "investigation": sample["investigation"],
        "retrieved_chunk_ids": ["chunk-0001", "chunk-0002"],
        "citations": [sample["citation"]],
        "review": sample["review"],
        "dossier": sample["dossier"],
        "budget": {"tokens_used": 960, "started_at": "2026-09-15T13:00:01Z"},
        "attempts": {"triage": 1, "investigation": 2, "reviewer": 1},
    }
    return _state(sample, **(full | {"state": "DRAFT_READY"} | overrides))


def _archive_triage(sample: dict[str, Any]) -> dict[str, Any]:
    return sample["triage"] | {"level": "PROPOR_ARQUIVAMENTO", "fired_rules": []}


def test_dt_envelope_estado_serializa_e_desserializa_sem_perda(sample: dict[str, Any]) -> None:
    state = InvestigationState.model_validate(_draft_ready(sample))

    assert InvestigationState.model_validate_json(state.model_dump_json()) == state
    assert InvestigationState.model_validate(state.model_dump()) == state
    assert state.attempts == {Node.TRIAGE: 1, Node.INVESTIGATION: 2, Node.REVIEWER: 1}
    assert state.model_dump(mode="json")["sanitized_alert"]["transactions"][0]["amount_brl"] == "9800.00"


def test_dt_envelope_estado_minimo_apos_sanitizacao(sample: dict[str, Any]) -> None:
    state = InvestigationState.model_validate(_state(sample))
    assert (state.triage, state.investigation, state.dossier, state.attempts) == (None, None, None, {})
    assert InvestigationState.model_validate_json(state.model_dump_json()) == state


def test_dt_envelope_estado_caminho_de_arquivamento_da_triagem(sample: dict[str, Any]) -> None:
    dossier = sample["dossier"] | {
        "type": "ARQUIVAMENTO",
        "typology": None,
        "cc4001_incisos": [],
        "evidence": [],
        "citations": [],
        "recommendation": "ARQUIVAR",
        "ai_generated_fields": [],
        "versions": {"rules": 1, "corpus": None, "mapping": None, "features": None, "prompt": None, "model": None},
    }
    state = InvestigationState.model_validate(
        _state(sample, "DRAFT_READY", triage=_archive_triage(sample), dossier=dossier)
    )
    assert state.dossier is not None


def test_dt_envelope_estado_needs_human_preserva_producao_parcial(sample: dict[str, Any]) -> None:
    partial = {"triage": sample["triage"], "features": sample["features"], "investigation": sample["investigation"]}
    state = InvestigationState.model_validate(
        _state(sample, "NEEDS_HUMAN", failure_reason="BUDGET_EXCEEDED", **partial)
    )
    assert state.investigation is not None
    with pytest.raises(ValidationError, match="failure_reason"):
        InvestigationState.model_validate(_state(sample, "NEEDS_HUMAN", **partial))


@pytest.mark.parametrize("nested", ["sanitized_alert", "triage", "features", "dossier"])
def test_dt_envelope_estado_com_contrato_de_outro_alerta_rejeitado(sample: dict[str, Any], nested: str) -> None:
    data = _draft_ready(sample)
    data[nested] = data[nested] | {"alert_id": OTHER_ALERT_ID}
    with pytest.raises(ValidationError, match="alert_id"):
        InvestigationState.model_validate(data)


def test_dt_envelope_estado_received_rejeitado(sample: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        InvestigationState.model_validate(_state(sample, "RECEIVED"))


@pytest.mark.parametrize(
    ("state", "overrides"),
    [
        ("SANITIZED", {"triage": "triage"}),
        ("TRIAGED", {}),
        ("INVESTIGATING", {"triage": "archive"}),
        ("RESEARCHING", {"triage": "triage", "features": "features"}),
        ("TRIAGED", {"triage": "archive", "features": "features"}),
        ("TRIAGED", {"triage": "archive", "retrieved_chunk_ids": ["chunk-0001"]}),
        ("TRIAGED", {"triage": "triage", "features": "features", "investigation": "investigation"}),
        ("INVESTIGATING", {"triage": "triage", "features": "features", "retrieved_chunk_ids": ["chunk-0001"]}),
        ("INVESTIGATING", {"triage": "triage", "features": "features", "citations": "citations"}),
        (
            "RESEARCHING",
            {"triage": "triage", "features": "features", "investigation": "investigation", "review": "review"},
        ),
        (
            "REVIEWING",
            {"triage": "triage", "features": "features", "investigation": "investigation", "dossier": "dossier"},
        ),
    ],
)
def test_dt_envelope_estado_incoerente_com_rf10_rejeitado(
    sample: dict[str, Any], state: str, overrides: dict[str, Any]
) -> None:
    samples = sample | {"archive": _archive_triage(sample), "citations": [sample["citation"]]}
    resolved = {key: samples[value] if isinstance(value, str) else value for key, value in overrides.items()}
    with pytest.raises(ValidationError):
        InvestigationState.model_validate(_state(sample, state, **resolved))


@pytest.mark.parametrize(
    "overrides",
    [
        {"dossier": None},
        {"state": "SUBMITTED"},
        {"features": None},
        {
            "investigation": {
                "typology_hypothesis": "Structuring",
                "confidence": 0.8,
                "recommendation": "COMUNICAR",
                "evidence_feature_ids": ["F99"],
            }
        },
        {"attempts": {"planner": 1}},
        {"attempts": {"triage": 0}},
        {"budget": {"tokens_used": -1, "started_at": "2026-09-15T13:00:01Z"}},
        {"sanitized_alert": None},
    ],
)
def test_dt_envelope_estado_campo_invalido_rejeitado(sample: dict[str, Any], overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        InvestigationState.model_validate(_draft_ready(sample, **overrides))


def test_dt_envelope_estado_dossie_investigado_com_triagem_de_arquivamento_rejeitado(sample: dict[str, Any]) -> None:
    data = _state(sample, "DRAFT_READY", triage=_archive_triage(sample), dossier=sample["dossier"])
    with pytest.raises(ValidationError):
        InvestigationState.model_validate(data)


@pytest.mark.parametrize(
    ("state", "artifacts"),
    [
        ("TRIAGED", ("triage",)),
        ("INVESTIGATING", ("triage", "features")),
        ("RESEARCHING", ("triage", "features", "investigation", "retrieved_chunk_ids")),
        ("REVIEWING", ("triage", "features", "investigation", "retrieved_chunk_ids", "citations", "review")),
    ],
)
def test_dt_envelope_estado_artefatos_ate_a_fase_atual_aceitos(
    sample: dict[str, Any], state: str, artifacts: tuple[str, ...]
) -> None:
    full = _draft_ready(sample)
    data = _state(sample, state, **{name: full[name] for name in artifacts})
    assert InvestigationState.model_validate(data).state == state
