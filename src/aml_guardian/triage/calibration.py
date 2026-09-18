"""Relatórios de calibração determinística no conjunto de desenvolvimento."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from aml_guardian.contracts.pipeline import TriageDecision

CRITICAL_TYPOLOGIES = (
    "Structuring",
    "Smurfing",
    "Deposit-Send",
    "Layered Fan-In",
    "Layered Fan-Out",
    "Stacked Bipartite",
)


def summarize_decisions(decisions: Iterable[TriageDecision]) -> dict[str, int]:
    """Resume decisões sem acessar payload ou rótulo de exemplos."""
    values = Counter(decision.level.value for decision in decisions)
    return {"investigar": values.get("INVESTIGAR", 0), "propor_arquivamento": values.get("PROPOR_ARQUIVAMENTO", 0)}
