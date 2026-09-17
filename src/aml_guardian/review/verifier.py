"""Revisor determinístico de citações normativas (T1.8, RF-07): sem LLM.

Verifica que cada `chunk_id` citado (1) fazia parte do conjunto efetivamente recuperado (MCP-03/Seleção) e
(2) existe no `corpus_version` vigente com o SHA-256 do trecho normalizado igual ao registrado no chunk (DT-08,
via MCP-04). Citação não verificada é removida da minuta e listada em `rejected_citations` (DT-10); a decisão de
mandar o alerta a `NEEDS_HUMAN` por falta de citação verificada fica no nó Dossiê (RF-08, `Dossier`, DT-11).
"""

from __future__ import annotations

from typing import Protocol

from aml_guardian.contracts.pipeline import Citation, RejectedCitation, ReviewVerdict
from aml_guardian.norms.normalize import text_sha256
from aml_guardian.norms.server import get_norm_passage


class NormPassageGetter(Protocol):
    """Assinatura de MCP-04 `get_norm_passage` (injetável em teste)."""

    def __call__(self, chunk_id: str, corpus_version: str) -> dict[str, object]: ...


def _verify_one(
    citation: Citation,
    retrieved_chunk_ids: set[str],
    corpus_version: str,
    getter: NormPassageGetter,
) -> tuple[Citation | None, RejectedCitation | None]:
    if citation.chunk_id not in retrieved_chunk_ids:
        return None, RejectedCitation(chunk_id=citation.chunk_id, reason="chunk_id fora dos chunks recuperados")

    resposta = getter(chunk_id=citation.chunk_id, corpus_version=corpus_version)
    if not isinstance(resposta, dict) or resposta.get("status") != "success":
        reason = f"chunk_id fora de corpus_version {corpus_version} vigente (MCP-04 404 lógico)"
        return None, RejectedCitation(chunk_id=citation.chunk_id, reason=reason)

    esperado = text_sha256(citation.quoted_text)
    if esperado != resposta["text_sha256"]:
        return None, RejectedCitation(chunk_id=citation.chunk_id, reason="trecho adulterado: SHA-256 não confere")

    return citation, None


def review_citations(
    citations: list[Citation],
    retrieved_chunk_ids: list[str],
    corpus_version: str,
    passage_getter: NormPassageGetter = get_norm_passage,
) -> ReviewVerdict:
    """Verifica cada citação contra o corpus vigente e os chunks recuperados; sem LLM (RF-07)."""
    recuperados = set(retrieved_chunk_ids)
    verified: list[Citation] = []
    rejected: list[RejectedCitation] = []

    for citation in citations:
        ok, bad = _verify_one(citation, recuperados, corpus_version, passage_getter)
        if ok is not None:
            verified.append(ok)
        else:
            rejected.append(bad)

    grounding_raw_ratio = len(verified) / len(citations) if citations else 0.0
    return ReviewVerdict(
        verified_citations=verified, rejected_citations=rejected, grounding_raw_ratio=grounding_raw_ratio
    )
