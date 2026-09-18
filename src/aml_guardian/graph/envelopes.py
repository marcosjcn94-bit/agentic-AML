"""Construção do envelope A2A (DT-14) nas transições do grafo (T1.10, AGENTS.md §5).

Transporte em processo (SPEC.md §9.3): o envelope nunca sai deste pacote nem é persistido no `InvestigationState`
(que já não tem campo para ele — mudar o contrato é decisão estrutural, Ask First). Ele só formaliza que cada
transição respeita a mesma aresta e o mesmo `schema_version` de um transporte em rede; `payload` incoerente com a
aresta declarada é rejeitado pelos validadores já existentes em `contracts/envelope.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from aml_guardian.contracts.envelope import EDGES, A2AEnvelope, MessageType, Node
from aml_guardian.contracts.ingestion import _Contract  # noqa: PLC2701 - mesmo tipo base do envelope


def build_envelope(
    *,
    from_node: Node,
    to_node: Node,
    alert_id: UUID,
    trace_id: UUID,
    payload: _Contract,
) -> A2AEnvelope:
    """Monta e valida o envelope da aresta; aresta ou `payload` incoerentes levantam `ValueError`."""
    edge = EDGES.get((from_node, to_node))
    if edge is None:
        raise ValueError(f"aresta {from_node} → {to_node} inexistente (AGENTS.md §5)")
    message_type, schema_version = edge
    return A2AEnvelope(
        message_id=uuid4(),
        alert_id=alert_id,
        trace_id=trace_id,
        from_node=from_node,
        to_node=to_node,
        type=message_type,
        schema_version=schema_version,
        payload=payload,
        created_at=datetime.now(UTC),
    )


def build_error_envelope(*, from_node: Node, alert_id: UUID, trace_id: UUID, failure_reason: str, attempt: int):
    """Envelope `ERROR` de `from_node` para `human_handoff` (AGENTS.md §2.8); mesmo formato para qualquer nó."""
    from aml_guardian.contracts.envelope import NodeError

    return build_envelope(
        from_node=from_node,
        to_node=Node.HUMAN_HANDOFF,
        alert_id=alert_id,
        trace_id=trace_id,
        payload=NodeError(failure_reason=failure_reason, node=from_node, attempt=attempt),
    )


__all__ = ["MessageType", "build_envelope", "build_error_envelope"]
