"""Helpers compartilhados pelos nós do grafo (T1.10): tentativa por nó e falha padronizada (AGENTS.md §2.8)."""

from __future__ import annotations

from pathlib import Path

from aml_guardian.contracts.envelope import Node
from aml_guardian.contracts.ingestion import AlertState
from aml_guardian.contracts.runtime import InvestigationState
from aml_guardian.graph.audit import record_node_event
from aml_guardian.graph.envelopes import build_error_envelope


def attempt_for(state: InvestigationState, node: Node) -> int:
    return state.attempts.get(node, 0) + 1


def attempts_update(state: InvestigationState, node: Node, attempt: int) -> dict[Node, int]:
    return {**state.attempts, node: attempt}


def handle_failure(
    state: InvestigationState,
    node: Node,
    attempt: int,
    reason: str,
    db_path: Path | None = None,
    **extra: object,
) -> dict[str, object]:
    """`NEEDS_HUMAN` preservando `extra` (produção parcial já calculada pelo próprio nó, AGENTS.md §2.8)."""
    try:
        build_error_envelope(
            from_node=node, alert_id=state.alert_id, trace_id=state.trace_id, failure_reason=reason, attempt=attempt
        )
    except Exception:  # noqa: BLE001 - o handoff acontece mesmo se o envelope de erro for irregular
        pass
    record_node_event(
        state.alert_id,
        node,
        attempt,
        f"{node.value.upper()}_FAILED",
        state.state,
        AlertState.NEEDS_HUMAN,
        db_path=db_path,
    )
    return {
        "state": AlertState.NEEDS_HUMAN,
        "failure_reason": reason,
        "attempts": attempts_update(state, node, attempt),
        **extra,
    }
