"""`Authorization: Bearer` por papel (T1.11, API-01/03/09, `SPEC.md` §9.1): token lido de variável de ambiente.

Nunca de `.env` — cada papel tem sua própria variável (`API_TOKEN_<PAPEL>`), lida a cada requisição para que os
testes usem `monkeypatch.setenv`/`delenv` sem reiniciar o processo. Token ausente ou não reconhecido → 401;
token válido de papel diferente do exigido pela rota → 403.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Callable
from typing import NoReturn

from fastapi import Header, HTTPException

from aml_guardian.contracts.runtime import Role

_ENV_VAR_BY_ROLE = {
    Role.SISTEMA: "API_TOKEN_SISTEMA",
    Role.ANALISTA: "API_TOKEN_ANALISTA",
    Role.COMPLIANCE_OFFICER: "API_TOKEN_COMPLIANCE_OFFICER",
}


def _error(status_code: int, code: str, message: str) -> NoReturn:
    raise HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _role_for_token(token: str) -> Role | None:
    for role, env_var in _ENV_VAR_BY_ROLE.items():
        expected = os.environ.get(env_var)
        if expected and secrets.compare_digest(token, expected):
            return role
    return None


def require_role(*allowed: Role) -> Callable[..., Role]:
    """Dependency do FastAPI: exige um dos papéis em `allowed` (401 sem token válido, 403 fora do papel)."""

    def _dependency(authorization: str | None = Header(default=None)) -> Role:
        if authorization is None or not authorization.startswith("Bearer "):
            _error(401, "UNAUTHORIZED", "Authorization: Bearer ausente ou malformado")
        token = authorization.removeprefix("Bearer ").strip()
        if not token:
            _error(401, "UNAUTHORIZED", "Bearer token vazio")
        role = _role_for_token(token)
        if role is None:
            _error(401, "UNAUTHORIZED", "token não reconhecido")
        if role not in allowed:
            _error(403, "FORBIDDEN", f"papel {role.value} sem permissão para este recurso")
        return role

    return _dependency
