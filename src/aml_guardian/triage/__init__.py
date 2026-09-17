"""Triagem inicial (T1.4, RF-03, DT-06): 4 detectores críticos determinísticos + decisão versionada."""

from aml_guardian.triage.engine import MCPIndisponivelError, RestrictionChecker, TriageResult, run_triage

__all__ = ["MCPIndisponivelError", "RestrictionChecker", "TriageResult", "run_triage"]
