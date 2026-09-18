"""Avaliador inicial do M1 (T1.13, RNF-03 informativa, `SPEC.md` §10): `scripts/evaluate.py` usa este pacote."""

from __future__ import annotations

from aml_guardian.eval.gates import GateResultado, avalia_gates
from aml_guardian.eval.latency import AmostraLatencia, mede_fluxo_investigar
from aml_guardian.eval.report import escreve_relatorio, monta_relatorio

__all__ = [
    "AmostraLatencia",
    "GateResultado",
    "avalia_gates",
    "escreve_relatorio",
    "mede_fluxo_investigar",
    "monta_relatorio",
]
