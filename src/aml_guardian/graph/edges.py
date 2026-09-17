"""Roteamento condicional entre nós (T1.10, AGENTS.md §5): `NEEDS_HUMAN` sempre desvia para `human_handoff`.

`InvestigationState.state` já reflete o resultado de cada nó (posto pelo próprio nó em `nodes.py`); o roteamento
só lê esse campo, sem repetir a lógica de decisão dos módulos de negócio.
"""

from __future__ import annotations

from langgraph.graph import END

from aml_guardian.contracts.envelope import Node
from aml_guardian.contracts.ingestion import AlertState, TriageLevel
from aml_guardian.contracts.runtime import InvestigationState


def _handoff_or(state: InvestigationState, next_node: Node) -> str:
    if state.state is AlertState.NEEDS_HUMAN:
        return Node.HUMAN_HANDOFF.value
    return next_node.value


def route_after_triage(state: InvestigationState) -> str:
    """`PROPOR_ARQUIVAMENTO` vai direto ao dossiê; `INVESTIGAR` segue para a Investigação (AGENTS.md §5)."""
    if state.state is AlertState.NEEDS_HUMAN:
        return Node.HUMAN_HANDOFF.value
    next_node = Node.INVESTIGATION if state.triage.level is TriageLevel.INVESTIGAR else Node.DOSSIER
    return next_node.value


def route_after_investigation(state: InvestigationState) -> str:
    return _handoff_or(state, Node.RETRIEVAL)


def route_after_retrieval(state: InvestigationState) -> str:
    return _handoff_or(state, Node.SELECTION)


def route_after_selection(state: InvestigationState) -> str:
    return _handoff_or(state, Node.REVIEWER)


def route_after_reviewer(state: InvestigationState) -> str:
    return _handoff_or(state, Node.DOSSIER)


def route_after_dossier(state: InvestigationState) -> str:
    if state.state is AlertState.NEEDS_HUMAN:
        return Node.HUMAN_HANDOFF.value
    return END
