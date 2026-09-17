"""Recuperação e seleção determinística de trechos normativos (T1.8, RF-06, ADR-013 A)."""

from aml_guardian.retrieval.query import NormSearchError, build_query, search_candidates
from aml_guardian.retrieval.selection import NormPassageError, select_citations

__all__ = [
    "NormPassageError",
    "NormSearchError",
    "build_query",
    "search_candidates",
    "select_citations",
]
