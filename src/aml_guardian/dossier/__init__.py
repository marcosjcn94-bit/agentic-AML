"""Montagem do dossiê por template Jinja2 (T1.9, RF-08): DT-11, sem texto livre de LLM."""

from aml_guardian.dossier.assembler import DossierResult, assemble_from_investigation, assemble_from_triage
from aml_guardian.dossier.renderer import render_dossier

__all__ = [
    "DossierResult",
    "assemble_from_investigation",
    "assemble_from_triage",
    "render_dossier",
]
