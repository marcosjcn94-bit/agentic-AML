"""Envelope A2A entre nós do grafo: DT-14 e registro `schema_version → modelo` (SPEC.md §9.3, AGENTS.md §5).

Nenhum envelope carrega dado pessoal em claro: todo `payload` é um contrato já sanitizado ou um erro estruturado.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Annotated, Any, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field, SerializeAsAny, model_validator

from aml_guardian.contracts.ingestion import NonEmptyStr, SanitizedAlert, _Contract
from aml_guardian.contracts.pipeline import (
    Citation,
    InvestigationFeatures,
    InvestigationOutput,
    ReviewVerdict,
    TriageDecision,
)

Attempt = Annotated[int, Field(strict=True, ge=1)]


class Node(StrEnum):
    """Nós que trocam DT-14 (AGENTS.md §1, §5)."""

    SANITIZER = "sanitizer"
    TRIAGE = "triage"
    INVESTIGATION = "investigation"
    RETRIEVAL = "retrieval"
    SELECTION = "selection"
    REVIEWER = "reviewer"
    DOSSIER = "dossier"
    HUMAN_HANDOFF = "human_handoff"


class MessageType(StrEnum):
    """Tipo da mensagem A2A (DT-14)."""

    TASK = "TASK"
    RESULT = "RESULT"
    ERROR = "ERROR"


class InvestigationTask(_Contract):
    """Payload `triage → investigation`: DT-04 + DT-06."""

    sanitized_alert: SanitizedAlert
    triage: TriageDecision


class InvestigationResult(_Contract):
    """Payload `investigation → retrieval`: DT-16 + DT-07 pós-processado (RF-05)."""

    features: InvestigationFeatures
    investigation: InvestigationOutput


class RetrievalResult(_Contract):
    """Payload `retrieval → selection`: `chunk_id`s recuperados, sem texto (MCP-03)."""

    retrieved_chunk_ids: list[NonEmptyStr]


class SelectionResult(_Contract):
    """Payload `selection → reviewer`: DT-09[]."""

    citations: list[Citation]


class NodeError(_Contract):
    """Payload `ERROR` de qualquer nó para `human_handoff` (AGENTS.md §2.8)."""

    failure_reason: NonEmptyStr
    node: Node
    attempt: Attempt


SCHEMA_REGISTRY: Mapping[str, type[_Contract]] = MappingProxyType(
    {
        "DT-04.v1": SanitizedAlert,
        "DT-06.v1": TriageDecision,
        "DT-04+DT-06.v1": InvestigationTask,
        "DT-16+DT-07.v1": InvestigationResult,
        "retrieved_chunk_ids.v1": RetrievalResult,
        "DT-09[].v1": SelectionResult,
        "DT-10.v1": ReviewVerdict,
        "error.v1": NodeError,
    }
)

_FLOW_EDGES = {
    (Node.SANITIZER, Node.TRIAGE): (MessageType.TASK, "DT-04.v1"),
    (Node.TRIAGE, Node.DOSSIER): (MessageType.TASK, "DT-06.v1"),
    (Node.TRIAGE, Node.INVESTIGATION): (MessageType.TASK, "DT-04+DT-06.v1"),
    (Node.INVESTIGATION, Node.RETRIEVAL): (MessageType.RESULT, "DT-16+DT-07.v1"),
    (Node.RETRIEVAL, Node.SELECTION): (MessageType.RESULT, "retrieved_chunk_ids.v1"),
    (Node.SELECTION, Node.REVIEWER): (MessageType.RESULT, "DT-09[].v1"),
    (Node.REVIEWER, Node.DOSSIER): (MessageType.RESULT, "DT-10.v1"),
}
_ERROR_EDGES = {
    (node, Node.HUMAN_HANDOFF): (MessageType.ERROR, "error.v1") for node in Node if node is not Node.HUMAN_HANDOFF
}

EDGES: Mapping[tuple[Node, Node], tuple[MessageType, str]] = MappingProxyType(_FLOW_EDGES | _ERROR_EDGES)
"""Arestas do AGENTS.md §5: `(from_node, to_node) → (type, schema_version)`; condições de roteamento ficam no grafo."""


def alert_ids(contract: BaseModel) -> set[UUID]:
    """`alert_id` do contrato e dos contratos aninhados no primeiro nível."""
    found: set[UUID] = set()
    for value in (contract, *(getattr(contract, name) for name in type(contract).model_fields)):
        if isinstance(value, BaseModel) and "alert_id" in type(value).model_fields:
            found.add(getattr(value, "alert_id"))  # noqa: B009 - campo dinâmico de subclasse
    return found


class A2AEnvelope(_Contract):
    """DT-14 — mensagem entre nós; `payload` validado pelo modelo registrado em `schema_version` (SPEC.md §9.3)."""

    message_id: UUID
    alert_id: UUID
    trace_id: UUID
    from_node: Node
    to_node: Node
    type: MessageType
    schema_version: NonEmptyStr
    payload: SerializeAsAny[_Contract]
    created_at: AwareDatetime

    @model_validator(mode="before")
    @classmethod
    def _payload_matches_schema_version(cls, data: Any) -> Any:
        """Troca o `payload` bruto pela instância do modelo registrado; versão fora do registro é recusada."""
        if not isinstance(data, dict):
            return data
        version = data.get("schema_version")
        schema = SCHEMA_REGISTRY.get(version) if isinstance(version, str) else None
        if schema is None:
            raise ValueError(f"schema_version fora do registro: {version!r}")
        return data | {"payload": schema.model_validate(data.get("payload"))}

    @model_validator(mode="after")
    def _route_matches_edge(self) -> Self:
        expected = EDGES.get((self.from_node, self.to_node))
        if expected is None:
            raise ValueError(f"aresta {self.from_node} → {self.to_node} inexistente (AGENTS.md §5)")
        if expected != (self.type, self.schema_version):
            raise ValueError(f"aresta {self.from_node} → {self.to_node} exige type/schema_version {expected}")
        return self

    @model_validator(mode="after")
    def _payload_of_same_alert(self) -> Self:
        if foreign := alert_ids(self.payload) - {self.alert_id}:
            raise ValueError(f"payload com alert_id de outro alerta: {sorted(map(str, foreign))}")
        return self
