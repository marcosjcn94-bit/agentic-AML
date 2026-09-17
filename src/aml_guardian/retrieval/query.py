"""Consulta por template a partir da tipologia e dos incisos mapeados (T1.8, RF-06).

A consulta nunca contém dado pessoal: só a tipologia (enum `Typology`) e os incisos do mapeamento versionado
(`aml_guardian.sourcedata.mapping`). `top_k` é fixo em 8 (SPEC.md §9.2, MCP-03); sem cache (RF-06).
"""

from __future__ import annotations

from typing import Protocol

from aml_guardian.contracts.pipeline import Typology
from aml_guardian.norms.server import search_norms
from aml_guardian.sourcedata.mapping import Tipologia

TOP_K = 8


class NormSearcher(Protocol):
    """Assinatura de MCP-03 `search_norms` (injetável em teste)."""

    def __call__(self, query: str, top_k: int, corpus_version: str) -> dict[str, object]: ...


class NormSearchError(RuntimeError):
    """MCP-03 indisponível ou com resposta fora do formato esperado (RF-06)."""


def build_query(typology: Typology, enquadramento: Tipologia) -> str:
    """Monta a consulta textual por template: tipologia + incisos mapeados, sem dado pessoal (RF-06)."""
    incisos = ", ".join(enquadramento.incisos)
    return f"{typology.value}: indícios enquadrados no art. 1º, incisos {incisos}, da CC 4.001/2020"


def search_candidates(
    typology: Typology,
    enquadramento: Tipologia,
    corpus_version: str,
    searcher: NormSearcher = search_norms,
) -> list[dict[str, object]]:
    """Consulta o MCP-03 (top_k = 8) e devolve os candidatos `{chunk_id, article_ref, score}` (RF-06)."""
    query = build_query(typology, enquadramento)
    resultado = searcher(query=query, top_k=TOP_K, corpus_version=corpus_version)
    if not isinstance(resultado, dict) or resultado.get("status") != "success":
        raise NormSearchError(f"MCP-03 respondeu fora do formato esperado: {resultado!r}")
    return resultado["results"]
