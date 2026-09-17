"""Nós `dossier` e `human_handoff` (T1.10): sink de sucesso e estado terminal de falha (RF-08, RF-09, ADR-011)."""

from __future__ import annotations

from aml_guardian.contracts.envelope import Node
from aml_guardian.contracts.ingestion import AlertState, TriageLevel
from aml_guardian.contracts.runtime import InvestigationState
from aml_guardian.deadlines.calculator import calculate_deadlines
from aml_guardian.dossier.assembler import assemble_from_investigation, assemble_from_triage
from aml_guardian.graph.audit import record_node_event
from aml_guardian.graph.deps import GraphDeps
from aml_guardian.graph.mapping_lookup import enquadramento_por_typology
from aml_guardian.graph.node_support import attempt_for, attempts_update, handle_failure
from aml_guardian.investigation.contract import PROMPT_VERSION
from aml_guardian.investigation.litellm_client import resolver_params
from aml_guardian.sourcedata.mapping import load_saml_d_mapping


def make_dossier_node(deps: GraphDeps):
    """`triage`(`PROPOR_ARQUIVAMENTO`) ou `reviewer` `→ dossier`: monta DT-11 por template (RF-08, RF-09)."""

    def _node(state: InvestigationState) -> dict[str, object]:
        attempt = attempt_for(state, Node.DOSSIER)
        try:
            deadlines = calculate_deadlines(state.sanitized_alert.selected_at)

            if state.triage.level is TriageLevel.PROPOR_ARQUIVAMENTO:
                resultado = assemble_from_triage(state.alert_id, state.triage, deadlines)
            else:
                mapping = deps.saml_mapping or load_saml_d_mapping()
                enquadramento = enquadramento_por_typology(mapping, state.investigation.typology_hypothesis)
                cc4001_incisos = list(enquadramento.incisos) if enquadramento is not None else []
                model_id = resolver_params(deps.litellm_config).model
                resultado = assemble_from_investigation(
                    state.alert_id,
                    state.investigation,
                    state.features,
                    state.review,
                    cc4001_incisos,
                    deadlines,
                    rules_version=state.triage.rules_version,
                    corpus_version=deps.corpus_version,
                    mapping_version=mapping.mapping_version,
                    prompt_version=PROMPT_VERSION,
                    model_id=model_id,
                )
        except Exception as exc:  # noqa: BLE001 - qualquer falha do nó é fail-closed
            return handle_failure(state, Node.DOSSIER, attempt, f"Dossiê falhou: {exc}", db_path=deps.db_path)

        if resultado.state is AlertState.NEEDS_HUMAN:
            return handle_failure(state, Node.DOSSIER, attempt, resultado.failure_reason, db_path=deps.db_path)

        record_node_event(
            state.alert_id,
            Node.DOSSIER,
            attempt,
            "DOSSIER_READY",
            state.state,
            AlertState.DRAFT_READY,
            db_path=deps.db_path,
        )
        return {
            "state": AlertState.DRAFT_READY,
            "dossier": resultado.dossier,
            "attempts": attempts_update(state, Node.DOSSIER, attempt),
        }

    return _node


def make_human_handoff_node(deps: GraphDeps):
    """Estado terminal de falha (RF-10, ADR-011): não altera `state`/`failure_reason`, só registra o handoff."""

    def _node(state: InvestigationState) -> dict[str, object]:
        attempt = attempt_for(state, Node.HUMAN_HANDOFF)
        record_node_event(
            state.alert_id,
            Node.HUMAN_HANDOFF,
            attempt,
            "HUMAN_HANDOFF",
            state.state,
            AlertState.NEEDS_HUMAN,
            db_path=deps.db_path,
        )
        return {"attempts": attempts_update(state, Node.HUMAN_HANDOFF, attempt)}

    return _node
