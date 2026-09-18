"""Nós `retrieval`, `selection` e `reviewer` (T1.10): sem enquadramento curado, seguem sem citação (RF-06/RF-07)."""

from __future__ import annotations

from aml_guardian.contracts.envelope import Node, RetrievalResult, SelectionResult
from aml_guardian.contracts.ingestion import AlertState
from aml_guardian.contracts.pipeline import Citation
from aml_guardian.contracts.runtime import InvestigationState
from aml_guardian.graph.audit import record_node_event
from aml_guardian.graph.deps import GraphDeps
from aml_guardian.graph.envelopes import build_envelope
from aml_guardian.graph.mapping_lookup import enquadramento_por_typology
from aml_guardian.graph.node_support import attempt_for, attempts_update, handle_failure
from aml_guardian.retrieval.query import NormSearchError, search_candidates
from aml_guardian.retrieval.selection import NormPassageError, select_citations
from aml_guardian.review.verifier import review_citations
from aml_guardian.sourcedata.mapping import load_saml_d_mapping


def make_retrieval_node(deps: GraphDeps):
    """`investigation → retrieval`: candidatos do MCP-03 (RF-06); sem candidatos vira lista vazia, não falha."""

    def _node(state: InvestigationState) -> dict[str, object]:
        attempt = attempt_for(state, Node.RETRIEVAL)
        try:
            mapping = deps.saml_mapping or load_saml_d_mapping()
            enquadramento = enquadramento_por_typology(mapping, state.investigation.typology_hypothesis)

            retrieved_chunk_ids: list[str] = []
            if enquadramento is not None:
                candidatos = search_candidates(
                    state.investigation.typology_hypothesis,
                    enquadramento,
                    deps.corpus_version,
                    deps.searcher,
                    cache=deps.norm_cache,
                )
                retrieved_chunk_ids = [candidato["chunk_id"] for candidato in candidatos]

            payload = RetrievalResult(retrieved_chunk_ids=retrieved_chunk_ids)
            build_envelope(
                from_node=Node.RETRIEVAL,
                to_node=Node.SELECTION,
                alert_id=state.alert_id,
                trace_id=state.trace_id,
                payload=payload,
            )
        except NormSearchError as exc:
            return handle_failure(state, Node.RETRIEVAL, attempt, f"MCP-03 indisponível: {exc}", db_path=deps.db_path)
        except Exception as exc:  # noqa: BLE001 - qualquer outra falha do nó é fail-closed
            return handle_failure(state, Node.RETRIEVAL, attempt, f"Recuperação falhou: {exc}", db_path=deps.db_path)

        record_node_event(
            state.alert_id,
            Node.RETRIEVAL,
            attempt,
            "RETRIEVAL_COMPLETED",
            AlertState.INVESTIGATING,
            AlertState.RESEARCHING,
            db_path=deps.db_path,
        )
        return {
            "state": AlertState.RESEARCHING,
            "retrieved_chunk_ids": retrieved_chunk_ids,
            "attempts": attempts_update(state, Node.RETRIEVAL, attempt),
        }

    return _node


def make_selection_node(deps: GraphDeps):
    """`retrieval → selection`: até 3 citações verificáveis (RF-06, ADR-013 A); sem enquadramento, nenhuma."""

    def _node(state: InvestigationState) -> dict[str, object]:
        attempt = attempt_for(state, Node.SELECTION)
        try:
            mapping = deps.saml_mapping or load_saml_d_mapping()
            enquadramento = enquadramento_por_typology(mapping, state.investigation.typology_hypothesis)

            citations: list[Citation] = []
            if enquadramento is not None:
                citations = select_citations(
                    state.investigation.typology_hypothesis,
                    enquadramento,
                    deps.corpus_version,
                    searcher=deps.searcher,
                    passage_getter=deps.passage_getter,
                    retrieval_cfg=deps.retrieval_cfg,
                )

            payload = SelectionResult(citations=citations)
            build_envelope(
                from_node=Node.SELECTION,
                to_node=Node.REVIEWER,
                alert_id=state.alert_id,
                trace_id=state.trace_id,
                payload=payload,
            )
        except (NormSearchError, NormPassageError) as exc:
            return handle_failure(
                state, Node.SELECTION, attempt, f"MCP indisponível na seleção: {exc}", db_path=deps.db_path
            )
        except Exception as exc:  # noqa: BLE001 - qualquer outra falha do nó é fail-closed
            return handle_failure(state, Node.SELECTION, attempt, f"Seleção falhou: {exc}", db_path=deps.db_path)

        record_node_event(
            state.alert_id,
            Node.SELECTION,
            attempt,
            "SELECTION_COMPLETED",
            AlertState.RESEARCHING,
            AlertState.REVIEWING,
            db_path=deps.db_path,
        )
        return {
            "state": AlertState.REVIEWING,
            "citations": citations,
            "attempts": attempts_update(state, Node.SELECTION, attempt),
        }

    return _node


def make_reviewer_node(deps: GraphDeps):
    """`selection → reviewer`: verifica cada citação por hash contra a `corpus_version` vigente (RF-07)."""

    def _node(state: InvestigationState) -> dict[str, object]:
        attempt = attempt_for(state, Node.REVIEWER)
        try:
            veredito = review_citations(
                state.citations, state.retrieved_chunk_ids, deps.corpus_version, deps.passage_getter
            )
        except Exception as exc:  # noqa: BLE001 - falha do nó é fail-closed
            return handle_failure(state, Node.REVIEWER, attempt, f"Revisor falhou: {exc}", db_path=deps.db_path)

        try:
            build_envelope(
                from_node=Node.REVIEWER,
                to_node=Node.DOSSIER,
                alert_id=state.alert_id,
                trace_id=state.trace_id,
                payload=veredito,
            )
        except Exception as exc:  # noqa: BLE001 - envelope inválido é a mesma falha fail-closed
            return handle_failure(
                state, Node.REVIEWER, attempt, f"Envelope reviewer→dossier inválido: {exc}", db_path=deps.db_path
            )

        record_node_event(
            state.alert_id,
            Node.REVIEWER,
            attempt,
            "REVIEW_COMPLETED",
            AlertState.REVIEWING,
            AlertState.REVIEWING,
            db_path=deps.db_path,
        )
        return {"review": veredito, "attempts": attempts_update(state, Node.REVIEWER, attempt)}

    return _node
