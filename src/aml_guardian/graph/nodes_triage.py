"""Nós `triage` e `investigation` (T1.10): sanitizador já rodou fora do grafo (AGENTS.md §1)."""

from __future__ import annotations

from aml_guardian.contracts.envelope import InvestigationResult as EnvInvestigationResult
from aml_guardian.contracts.envelope import InvestigationTask, Node
from aml_guardian.contracts.ingestion import AlertState, TriageLevel
from aml_guardian.contracts.runtime import InvestigationState
from aml_guardian.graph.audit import record_node_event
from aml_guardian.graph.deps import GraphDeps
from aml_guardian.graph.envelopes import build_envelope
from aml_guardian.graph.node_support import attempt_for, attempts_update, handle_failure
from aml_guardian.investigation.litellm_client import ContadorChamadas
from aml_guardian.investigation.runner import run_investigation
from aml_guardian.triage.engine import run_triage


def make_triage_node(deps: GraphDeps):
    """`sanitizer → triage`: decide `TRIAGED` (DT-06) ou `NEEDS_HUMAN` sem MCP-02 (AGENTS.md §2.2)."""

    def _node(state: InvestigationState) -> dict[str, object]:
        attempt = attempt_for(state, Node.TRIAGE)
        try:
            resultado = run_triage(
                state.sanitized_alert, rules=deps.triage_rules, restriction_checker=deps.restriction_checker
            )
        except Exception as exc:  # noqa: BLE001 - qualquer falha do nó é fail-closed
            return handle_failure(state, Node.TRIAGE, attempt, f"Triagem falhou: {exc}")
        if resultado.state is AlertState.NEEDS_HUMAN:
            return handle_failure(state, Node.TRIAGE, attempt, resultado.failure_reason)

        to_node = Node.INVESTIGATION if resultado.decision.level is TriageLevel.INVESTIGAR else Node.DOSSIER
        try:
            payload = (
                InvestigationTask(sanitized_alert=state.sanitized_alert, triage=resultado.decision)
                if to_node is Node.INVESTIGATION
                else resultado.decision
            )
            build_envelope(
                from_node=Node.TRIAGE,
                to_node=to_node,
                alert_id=state.alert_id,
                trace_id=state.trace_id,
                payload=payload,
            )
        except Exception as exc:  # noqa: BLE001 - payload/envelope inválido é a mesma falha fail-closed
            return handle_failure(state, Node.TRIAGE, attempt, f"Envelope triagem→{to_node.value} inválido: {exc}")

        record_node_event(
            state.alert_id, Node.TRIAGE, attempt, "TRIAGE_DECIDED", AlertState.SANITIZED, AlertState.TRIAGED
        )
        return {
            "state": AlertState.TRIAGED,
            "triage": resultado.decision,
            "attempts": attempts_update(state, Node.TRIAGE, attempt),
        }

    return _node


def make_investigation_node(deps: GraphDeps):
    """`triage → investigation`: pré-passo + LLM + pós-processamento RF-05 (só roda em `TriageLevel.INVESTIGAR`)."""

    def _node(state: InvestigationState) -> dict[str, object]:
        attempt = attempt_for(state, Node.INVESTIGATION)
        try:
            resultado = run_investigation(
                state.sanitized_alert,
                state.triage,
                triage_rules=deps.triage_rules,
                litellm_config=deps.litellm_config,
                saml_mapping=deps.saml_mapping,
                history_fetcher=deps.history_fetcher,
                restriction_checker=deps.restriction_checker,
                contador=deps.contador or ContadorChamadas(),
                **deps.model_overrides,
            )
        except Exception as exc:  # noqa: BLE001 - falha do nó é fail-closed
            return handle_failure(state, Node.INVESTIGATION, attempt, f"Investigação falhou: {exc}")

        extra: dict[str, object] = {}
        if resultado.features is not None:
            extra["features"] = resultado.features
        if resultado.investigation is not None:
            extra["investigation"] = resultado.investigation
        if resultado.state is AlertState.NEEDS_HUMAN:
            return handle_failure(state, Node.INVESTIGATION, attempt, resultado.failure_reason, **extra)

        try:
            payload = EnvInvestigationResult(features=resultado.features, investigation=resultado.investigation)
            build_envelope(
                from_node=Node.INVESTIGATION,
                to_node=Node.RETRIEVAL,
                alert_id=state.alert_id,
                trace_id=state.trace_id,
                payload=payload,
            )
        except Exception as exc:  # noqa: BLE001 - payload/envelope inválido é a mesma falha fail-closed
            return handle_failure(
                state, Node.INVESTIGATION, attempt, f"Envelope investigação→retrieval inválido: {exc}", **extra
            )

        record_node_event(
            state.alert_id,
            Node.INVESTIGATION,
            attempt,
            "INVESTIGATION_COMPLETED",
            AlertState.TRIAGED,
            AlertState.INVESTIGATING,
        )
        return {
            "state": AlertState.INVESTIGATING,
            **extra,
            "attempts": attempts_update(state, Node.INVESTIGATION, attempt),
        }

    return _node
