"""Servidores MCP-03 (`search_norms`) e MCP-04 (`get_norm_passage`) — T1.7, `SPEC.md` §9.2, RF-06.

Mesma convenção de erro dos servidores MCP-01/MCP-02 (`aml_guardian.mcp_servers.server`, T1.3): função pura que
devolve `{"status": "success", ...}` ou `{"error", "message", "retryable"}`. MCP-03 nunca devolve texto do
trecho (só `chunk_id`, `article_ref`, `score`); MCP-04 devolve o DT-08 completo ou 404 lógico.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from aml_guardian.norms.store import NormsStore

MAX_TOP_K = 8


@lru_cache(maxsize=1)
def _default_store() -> NormsStore:
    return NormsStore()


def search_norms(query: str, top_k: int, corpus_version: str, store: NormsStore | None = None) -> dict[str, Any]:
    """MCP-03: busca vetorial na coleção `norms`; `top_k` fora de 1..8 é rejeitado sem tocar a store."""
    if isinstance(top_k, bool) or not isinstance(top_k, int) or not (1 <= top_k <= MAX_TOP_K):
        return {
            "error": "INVALID_PARAMETER",
            "message": f"top_k deve estar entre 1 e {MAX_TOP_K}, recebido {top_k!r}",
            "retryable": False,
        }
    if not query or not query.strip():
        return {"error": "INVALID_PARAMETER", "message": "query vazia", "retryable": False}

    active_store = store or _default_store()
    try:
        results = active_store.search(query=query, top_k=top_k, corpus_version=corpus_version)
    except Exception as exc:  # noqa: BLE001 - qualquer falha da store é indisponibilidade do MCP-03
        return {"error": "INTERNAL_ERROR", "message": str(exc), "retryable": True}

    return {"status": "success", "results": results}


def get_norm_passage(chunk_id: str, corpus_version: str, store: NormsStore | None = None) -> dict[str, Any]:
    """MCP-04: devolve o DT-08 completo de `chunk_id`; 404 lógico se não pertencer a `corpus_version`."""
    active_store = store or _default_store()
    try:
        chunk = active_store.get_chunk(chunk_id, corpus_version)
    except Exception as exc:  # noqa: BLE001 - qualquer falha da store é indisponibilidade do MCP-04
        return {"error": "INTERNAL_ERROR", "message": str(exc), "retryable": True}

    if chunk is None:
        return {
            "error": "NOT_FOUND",
            "message": f"chunk_id {chunk_id!r} não pertence a corpus_version {corpus_version!r}",
            "retryable": False,
        }

    return {
        "status": "success",
        "chunk_id": chunk.chunk_id,
        "doc_id": chunk.doc_id,
        "article_ref": chunk.article_ref,
        "text": chunk.text,
        "text_sha256": chunk.text_sha256,
        "corpus_version": chunk.corpus_version,
        "source_url": str(chunk.source_url),
    }
