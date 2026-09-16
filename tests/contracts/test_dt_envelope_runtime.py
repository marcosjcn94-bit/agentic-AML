"""Contratos de auditoria, caso de sanitização e aprovação (DT-12, DT-13, DT-15; SPEC.md §8.2, RF-11, RF-12; T0.4).

Dados sintéticos; hashes calculados em tempo de execução, sem conteúdo real de prompt.
"""

from __future__ import annotations

import hashlib
from typing import Any

import pytest
from pydantic import ValidationError

from aml_guardian.contracts.runtime import (
    MIN_JUSTIFICATION_CHARS,
    Approval,
    ApprovalDecision,
    AuditEvent,
    Role,
    SanitizationTestCase,
)

ALERT_ID = "8f5c2a1e-3b7d-4c9a-9e21-6a0f4d2b7c11"
OTHER_ALERT_ID = "11111111-2222-4333-8444-555555555555"
HASH_1 = hashlib.sha256(b"evento-sintetico-1").hexdigest()
HASH_2 = hashlib.sha256(b"evento-sintetico-2").hexdigest()
PROMPT_SHA = hashlib.sha256(b"prompt-sintetico").hexdigest()

RF11_FIELDS = [
    "alert_id",
    "event_type",
    "actor",
    "state_from",
    "state_to",
    "model_id",
    "prompt_sha256",
    "rules_version",
    "corpus_version",
    "mapping_version",
    "prompt_version",
    "tokens_in",
    "tokens_out",
    "latency_ms",
    "prev_hash",
    "hash",
]


# DT-12 -----------------------------------------------------------------------


def _event(**overrides: object) -> dict[str, Any]:
    event: dict[str, Any] = {
        "seq": 2,
        "event_key": f"{ALERT_ID}:investigation:1",
        "occurred_at": "2026-09-15T13:00:10Z",
        "alert_id": ALERT_ID,
        "event_type": "NODE_COMPLETED",
        "actor": "sistema",
        "state_from": "TRIAGED",
        "state_to": "INVESTIGATING",
        "model_id": "ollama/qwen2.5:1.5b",
        "prompt_sha256": PROMPT_SHA,
        "rules_version": 1,
        "corpus_version": "corpus-0001",
        "mapping_version": 1,
        "prompt_version": "v1",
        "tokens_in": 900,
        "tokens_out": 60,
        "latency_ms": 8200,
        "prev_hash": HASH_1,
        "hash": HASH_2,
    }
    event.update(overrides)
    return event


def _deterministic_event(**overrides: object) -> dict[str, Any]:
    llm_free = {"model_id": None, "prompt_sha256": None, "prompt_version": None, "tokens_in": 0, "tokens_out": 0}
    return _event(**(llm_free | overrides))


def test_dt_envelope_auditoria_valida_com_e_sem_llm() -> None:
    assert AuditEvent.model_validate(_event()).actor is Role.SISTEMA
    first = AuditEvent.model_validate(
        _deterministic_event(seq=1, prev_hash=None, event_type="ALERT_RECEIVED", state_from=None, state_to="RECEIVED")
    )
    assert first.prev_hash is None


@pytest.mark.parametrize("field", [*RF11_FIELDS, "seq", "event_key", "occurred_at"])
def test_dt_envelope_auditoria_sem_campo_do_rf11_rejeitada(field: str) -> None:
    event = _event()
    del event[field]
    with pytest.raises(ValidationError):
        AuditEvent.model_validate(event)


@pytest.mark.parametrize(("seq", "prev_hash"), [(1, HASH_1), (2, None), (0, None)])
def test_dt_envelope_auditoria_encadeamento_inconsistente_rejeitado(seq: int, prev_hash: str | None) -> None:
    with pytest.raises(ValidationError):
        AuditEvent.model_validate(_event(seq=seq, prev_hash=prev_hash))


@pytest.mark.parametrize(
    "overrides",
    [
        {"event_key": f"{OTHER_ALERT_ID}:investigation:1"},
        {"hash": "A" * 64},
        {"prompt_sha256": "prompt completo em claro"},
        {"actor": "Cliente Sintético Um"},
        {"event_type": "evento livre com texto"},
        {"state_to": None},
        {"prompt_sha256": None},
        {"tokens_in": 1.5},
        {"latency_ms": -1},
        {"rules_version": "1"},
        {"cpf": "CPF_01"},
    ],
)
def test_dt_envelope_auditoria_campo_invalido_rejeitado(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        AuditEvent.model_validate(_event(**overrides))


def test_dt_envelope_auditoria_tokens_sem_modelo_rejeitados() -> None:
    with pytest.raises(ValidationError, match="model_id"):
        AuditEvent.model_validate(_deterministic_event(tokens_out=10))


# DT-13 -----------------------------------------------------------------------


def _case(text: str, *entities: tuple[str, int, int]) -> dict[str, Any]:
    return {"text": text, "expected_entities": [{"type": t, "start": s, "end": e} for t, s, e in entities]}


def test_dt_envelope_caso_de_sanitizacao_valido_preserva_offsets() -> None:
    text = "  Pagamento de NOME_SINT para conta 0001-9."
    case = SanitizationTestCase.model_validate(_case(text, ("NOME", 15, 24), ("CONTA", 35, 41)))
    assert case.text == text
    assert SanitizationTestCase.model_validate(_case("sem dado pessoal")).expected_entities == []


@pytest.mark.parametrize(
    "entities",
    [
        [("NOME", 0, 99)],
        [("NOME", 5, 5)],
        [("NOME", 6, 5)],
        [("NOME", -1, 3)],
        [("NOME", 0, 6), ("CPF", 5, 9)],
        [("nome", 0, 4)],
    ],
)
def test_dt_envelope_caso_de_sanitizacao_com_entidade_invalida_rejeitado(entities: list[tuple[str, int, int]]) -> None:
    with pytest.raises(ValidationError):
        SanitizationTestCase.model_validate(_case("Texto sintético qualquer", *entities))


# DT-15 -----------------------------------------------------------------------


def _approval(**overrides: object) -> dict[str, Any]:
    approval: dict[str, Any] = {
        "alert_id": ALERT_ID,
        "decision": "COMUNICAR",
        "justification": "x" * MIN_JUSTIFICATION_CHARS,
        "decided_by_role": "compliance_officer",
        "decided_at": "2026-09-18T20:00:00-03:00",
        "prazo_comunicacao": "2026-09-21",
    }
    approval.update(overrides)
    return approval


def test_dt_envelope_aprovacao_com_50_caracteres_aceita() -> None:
    assert MIN_JUSTIFICATION_CHARS == 50
    assert Approval.model_validate(_approval()).decision is ApprovalDecision.COMUNICAR
    returned = Approval.model_validate(_approval(decision="DEVOLVER", prazo_comunicacao=None))
    assert returned.prazo_comunicacao is None


@pytest.mark.parametrize("justification", ["x" * 49, " " * 10 + "x" * 49 + " " * 10, " " * 60])
def test_dt_envelope_aprovacao_com_49_caracteres_rejeitada(justification: str) -> None:
    with pytest.raises(ValidationError):
        Approval.model_validate(_approval(justification=justification))


@pytest.mark.parametrize(
    "overrides",
    [
        {"decided_by_role": "analista"},
        {"decided_by_role": "sistema"},
        {"decision": "APROVAR"},
        {"prazo_comunicacao": None},
        {"decision": "ARQUIVAR"},
        {"prazo_comunicacao": "2026-09-17"},
        {"prazo_comunicacao": "2026-09-18"},
        {"prazo_comunicacao": "2026-09-19"},
        {"decided_at": "2026-09-18T20:00:00"},
    ],
)
def test_dt_envelope_aprovacao_invalida_rejeitada(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Approval.model_validate(_approval(**overrides))


def test_dt_envelope_aprovacao_decisao_noturna_usa_data_de_brasilia() -> None:
    late = Approval.model_validate(_approval(decided_at="2026-09-21T22:30:00-03:00", prazo_comunicacao="2026-09-22"))
    assert late.prazo_comunicacao is not None and late.prazo_comunicacao.isoformat() == "2026-09-22"
