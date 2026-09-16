"""Contrato do envelope A2A e registro `schema_version → modelo` (DT-14; SPEC.md §9.3, AGENTS.md §5; T0.4)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from aml_guardian.contracts.envelope import EDGES, SCHEMA_REGISTRY, A2AEnvelope, MessageType, Node
from aml_guardian.contracts.ingestion import SanitizedAlert
from aml_guardian.contracts.pipeline import TriageDecision

ALERT_ID = "8f5c2a1e-3b7d-4c9a-9e21-6a0f4d2b7c11"
OTHER_ALERT_ID = "11111111-2222-4333-8444-555555555555"


def _envelope(from_node: str, to_node: str, type_: str, schema_version: str, payload: Any) -> dict[str, Any]:
    return {
        "message_id": "5d1b7c3e-9f2a-4b6c-8d0e-1a2b3c4d5e6f",
        "alert_id": ALERT_ID,
        "trace_id": "7a6b5c4d-3e2f-4a1b-9c8d-7e6f5a4b3c2d",
        "from_node": from_node,
        "to_node": to_node,
        "type": type_,
        "schema_version": schema_version,
        "payload": payload,
        "created_at": "2026-09-15T13:00:02Z",
    }


def _payloads(sample: dict[str, Any]) -> dict[str, Any]:
    return {
        "DT-04.v1": sample["sanitized_alert"],
        "DT-06.v1": sample["triage"],
        "DT-04+DT-06.v1": {"sanitized_alert": sample["sanitized_alert"], "triage": sample["triage"]},
        "DT-16+DT-07.v1": {"features": sample["features"], "investigation": sample["investigation"]},
        "retrieved_chunk_ids.v1": {"retrieved_chunk_ids": ["chunk-0001", "chunk-0002"]},
        "DT-09[].v1": {"citations": [sample["citation"]]},
        "DT-10.v1": sample["review"],
        "error.v1": {"failure_reason": "TIMEOUT", "node": "investigation", "attempt": 3},
    }


def test_dt_envelope_tipos_e_nos() -> None:
    assert {t.value for t in MessageType} == {"TASK", "RESULT", "ERROR"}
    assert {n.value for n in Node} == {
        "sanitizer",
        "triage",
        "investigation",
        "retrieval",
        "selection",
        "reviewer",
        "dossier",
        "human_handoff",
    }


def test_dt_envelope_registro_cobre_exatamente_as_arestas() -> None:
    assert {schema for _, schema in EDGES.values()} == set(SCHEMA_REGISTRY)
    with pytest.raises(TypeError):
        SCHEMA_REGISTRY["novo.v1"] = SanitizedAlert  # type: ignore[index]


def test_dt_envelope_erro_de_qualquer_no_para_encaminhamento_humano() -> None:
    senders = {
        src for (src, dst), (type_, _) in EDGES.items() if dst is Node.HUMAN_HANDOFF and type_ is MessageType.ERROR
    }
    assert senders == set(Node) - {Node.HUMAN_HANDOFF}


@pytest.mark.parametrize(("from_node", "to_node"), [(src.value, dst.value) for src, dst in EDGES])
def test_dt_envelope_aresta_valida_instancia_modelo_do_registro(
    sample: dict[str, Any], from_node: str, to_node: str
) -> None:
    type_, schema = EDGES[(Node(from_node), Node(to_node))]
    envelope = A2AEnvelope.model_validate(_envelope(from_node, to_node, type_, schema, _payloads(sample)[schema]))
    assert type(envelope.payload) is SCHEMA_REGISTRY[schema]


def test_dt_envelope_payload_divergente_do_schema_version_rejeitado(sample: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        A2AEnvelope.model_validate(_envelope("sanitizer", "triage", "TASK", "DT-04.v1", sample["triage"]))


def test_dt_envelope_instancia_de_outro_modelo_rejeitada(sample: dict[str, Any]) -> None:
    triage = TriageDecision.model_validate(sample["triage"])
    with pytest.raises(ValidationError):
        A2AEnvelope.model_validate(_envelope("sanitizer", "triage", "TASK", "DT-04.v1", triage))


@pytest.mark.parametrize("schema_version", ["DT-99.v1", "dt-04.v1", "", None, ["DT-04.v1"]])
def test_dt_envelope_schema_version_fora_do_registro_rejeitado(sample: dict[str, Any], schema_version: Any) -> None:
    with pytest.raises(ValidationError):
        A2AEnvelope.model_validate(_envelope("sanitizer", "triage", "TASK", schema_version, sample["sanitized_alert"]))


@pytest.mark.parametrize("type_", ["COMMAND", "task", "", None])
def test_dt_envelope_type_fora_do_enum_rejeitado(sample: dict[str, Any], type_: Any) -> None:
    with pytest.raises(ValidationError):
        A2AEnvelope.model_validate(_envelope("sanitizer", "triage", type_, "DT-04.v1", sample["sanitized_alert"]))


def test_dt_envelope_type_incoerente_com_a_aresta_rejeitado(sample: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="aresta"):
        A2AEnvelope.model_validate(_envelope("sanitizer", "triage", "RESULT", "DT-04.v1", sample["sanitized_alert"]))


@pytest.mark.parametrize(
    ("from_node", "to_node", "type_", "schema"),
    [
        ("triage", "reviewer", "TASK", "DT-06.v1"),
        ("human_handoff", "triage", "TASK", "DT-06.v1"),
        ("human_handoff", "human_handoff", "ERROR", "error.v1"),
        ("reviewer", "dossier", "ERROR", "error.v1"),
    ],
)
def test_dt_envelope_aresta_fora_do_agents_rejeitada(
    sample: dict[str, Any], from_node: str, to_node: str, type_: str, schema: str
) -> None:
    with pytest.raises(ValidationError, match="aresta"):
        A2AEnvelope.model_validate(_envelope(from_node, to_node, type_, schema, _payloads(sample)[schema]))


def test_dt_envelope_payload_de_outro_alerta_rejeitado(sample: dict[str, Any]) -> None:
    triage = sample["triage"] | {"alert_id": OTHER_ALERT_ID}
    payload = {"sanitized_alert": sample["sanitized_alert"], "triage": triage}
    with pytest.raises(ValidationError, match="alert_id"):
        A2AEnvelope.model_validate(_envelope("triage", "investigation", "TASK", "DT-04+DT-06.v1", payload))


def test_dt_envelope_payload_com_campo_extra_rejeitado(sample: dict[str, Any]) -> None:
    payload = {"failure_reason": "TIMEOUT", "node": "triage", "attempt": 1, "cpf": "CPF_01"}
    with pytest.raises(ValidationError):
        A2AEnvelope.model_validate(_envelope("triage", "human_handoff", "ERROR", "error.v1", payload))


@pytest.mark.parametrize("attempt", [0, -1, "1", 1.0])
def test_dt_envelope_erro_com_attempt_invalido_rejeitado(attempt: Any) -> None:
    payload = {"failure_reason": "TIMEOUT", "node": "triage", "attempt": attempt}
    with pytest.raises(ValidationError):
        A2AEnvelope.model_validate(_envelope("triage", "human_handoff", "ERROR", "error.v1", payload))


@pytest.mark.parametrize("schema", ["DT-04+DT-06.v1", "DT-16+DT-07.v1", "DT-09[].v1", "error.v1"])
def test_dt_envelope_serializa_e_desserializa_sem_perda(sample: dict[str, Any], schema: str) -> None:
    (from_node, to_node), _ = next((edge, v) for edge, v in EDGES.items() if v[1] == schema)
    type_ = EDGES[(from_node, to_node)][0]
    envelope = A2AEnvelope.model_validate(_envelope(from_node, to_node, type_, schema, _payloads(sample)[schema]))

    from_json = A2AEnvelope.model_validate_json(envelope.model_dump_json())
    from_python = A2AEnvelope.model_validate(envelope.model_dump())

    assert from_json == envelope
    assert from_python == envelope
    assert envelope.model_dump(mode="json")["payload"] == SCHEMA_REGISTRY[schema].model_validate(
        _payloads(sample)[schema]
    ).model_dump(mode="json")
