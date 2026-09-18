"""Corpo de erro uniforme `{error: {code, message, trace_id}}` (T1.11, `SPEC.md` §9.1): sem dado pessoal.

A mensagem de validação (422) nunca ecoa o valor enviado pelo cliente: só `loc` (caminho do campo) e `type`
(motivo pydantic), nunca `input` (RF-01 — corpo de erro não é destino de dado pessoal).
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def _body(code: str, message: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": code, "message": message, "trace_id": str(uuid4())}}


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:  # noqa: ARG001
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail and "message" in detail:
        return JSONResponse(status_code=exc.status_code, content=_body(str(detail["code"]), str(detail["message"])))
    return JSONResponse(status_code=exc.status_code, content=_body("HTTP_ERROR", str(detail)))


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:  # noqa: ARG001
    message = "; ".join(f"{'.'.join(str(part) for part in err['loc'])}: {err['type']}" for err in exc.errors())
    return JSONResponse(status_code=422, content=_body("VALIDATION_ERROR", message))


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
