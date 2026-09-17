"""API FastAPI do fluxo ponta a ponta (T1.11, API-01, API-03, API-09, `SPEC.md` §9.1)."""

from __future__ import annotations

from aml_guardian.api.app import create_app
from aml_guardian.api.state import AppState

__all__ = ["AppState", "create_app"]
