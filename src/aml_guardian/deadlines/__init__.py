"""Prazos do dossiê (T1.9, RF-09): +5 dias corridos (interno) e +45 dias (regulatório), persistidos em DT-05."""

from aml_guardian.deadlines.calculator import PRAZO_INTERNO_DIAS, PRAZO_REGULATORIO_DIAS, calculate_deadlines
from aml_guardian.deadlines.repository import get_deadlines, save_deadlines

__all__ = [
    "PRAZO_INTERNO_DIAS",
    "PRAZO_REGULATORIO_DIAS",
    "calculate_deadlines",
    "get_deadlines",
    "save_deadlines",
]
