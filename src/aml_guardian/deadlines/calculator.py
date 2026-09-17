"""Cálculo dos prazos do dossiê (T1.9, RF-09, SPEC.md §3.1): +5 dias corridos e +45 dias da seleção.

`timedelta(days=N)` soma dias corridos (calendário civil), atravessando virada de mês/ano corretamente por
construção do `datetime` do Python — não há regra de dia útil aqui (essa fica em `prazo_comunicacao`, RF-09,
fora do escopo do T1.9).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from aml_guardian.contracts.pipeline import DossierDeadlines

PRAZO_INTERNO_DIAS = 5
PRAZO_REGULATORIO_DIAS = 45


def calculate_deadlines(selecao_em: datetime) -> DossierDeadlines:
    """`prazo_interno = selecao_em + 5 dias corridos`; `prazo_regulatorio_analise = selecao_em + 45 dias` (RF-09)."""
    return DossierDeadlines(
        selecao_em=selecao_em,
        prazo_interno=selecao_em + timedelta(days=PRAZO_INTERNO_DIAS),
        prazo_regulatorio_analise=selecao_em + timedelta(days=PRAZO_REGULATORIO_DIAS),
    )
