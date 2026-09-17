"""Monta e invoca o grafo (T1.10): 7 nós de `AGENTS.md` §1, START em `triage`, checkpoint por super-step."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from aml_guardian.contracts.envelope import Node
from aml_guardian.contracts.runtime import InvestigationState
from aml_guardian.graph.deps import GraphDeps
from aml_guardian.graph.edges import (
    route_after_dossier,
    route_after_investigation,
    route_after_retrieval,
    route_after_reviewer,
    route_after_selection,
    route_after_triage,
)
from aml_guardian.graph.nodes_dossier import make_dossier_node, make_human_handoff_node
from aml_guardian.graph.nodes_retrieval import make_retrieval_node, make_reviewer_node, make_selection_node
from aml_guardian.graph.nodes_triage import make_investigation_node, make_triage_node


def build_graph(deps: GraphDeps) -> StateGraph:
    """Grafo não compilado: `build_graph(deps).compile(checkpointer=...)` (`run_alert` já faz isso)."""
    graph = StateGraph(InvestigationState)
    graph.add_node(Node.TRIAGE.value, make_triage_node(deps))
    graph.add_node(Node.INVESTIGATION.value, make_investigation_node(deps))
    graph.add_node(Node.RETRIEVAL.value, make_retrieval_node(deps))
    graph.add_node(Node.SELECTION.value, make_selection_node(deps))
    graph.add_node(Node.REVIEWER.value, make_reviewer_node(deps))
    graph.add_node(Node.DOSSIER.value, make_dossier_node(deps))
    graph.add_node(Node.HUMAN_HANDOFF.value, make_human_handoff_node(deps))

    graph.add_edge(START, Node.TRIAGE.value)
    graph.add_conditional_edges(Node.TRIAGE.value, route_after_triage)
    graph.add_conditional_edges(Node.INVESTIGATION.value, route_after_investigation)
    graph.add_conditional_edges(Node.RETRIEVAL.value, route_after_retrieval)
    graph.add_conditional_edges(Node.SELECTION.value, route_after_selection)
    graph.add_conditional_edges(Node.REVIEWER.value, route_after_reviewer)
    graph.add_conditional_edges(Node.DOSSIER.value, route_after_dossier)
    graph.add_edge(Node.HUMAN_HANDOFF.value, END)
    return graph


def run_alert(
    initial_state: InvestigationState,
    deps: GraphDeps,
    checkpointer: Any,
    thread_id: str | None = None,
) -> tuple[InvestigationState, Any, dict[str, Any]]:
    """Compila, invoca e reconstrói o `InvestigationState`; devolve também o grafo compilado e o `config`.

    O grafo compilado e o `config` são devolvidos para quem precisa inspecionar o checkpoint (`get_state_history`)
    sem recompilar — o checkpointer só existe dentro do `with` de `graph.checkpoint.sqlite_checkpointer`.
    """
    compiled = build_graph(deps).compile(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": thread_id or str(initial_state.alert_id)}}
    resultado = compiled.invoke(initial_state, config=config)
    return InvestigationState.model_validate(resultado), compiled, config
