"""Monta o FastAPI (T1.11): `app.state.aml` carrega o `AppState` de produção por padrão.

`create_app` aceita um `AppState` já pronto — é o ponto de injeção dos testes (`GraphDeps`/`HealthDeps` falsos,
sem tocar `data/app.sqlite` real nem a rede), no mesmo espírito de `run_alert(deps=...)` da T1.10.
"""

from __future__ import annotations

from fastapi import FastAPI

from aml_guardian.api.errors import register_exception_handlers
from aml_guardian.api.health import HealthDeps
from aml_guardian.api.routes import router
from aml_guardian.api.state import AppState
from aml_guardian.graph.deps import GraphDeps
from aml_guardian.persistence.db import init_db


def _default_app_state() -> AppState:
    init_db()
    return AppState(
        graph_deps=GraphDeps(corpus_version="unknown"),
        health_deps=HealthDeps(),
    )


def create_app(state: AppState | None = None) -> FastAPI:
    """Fábrica do app: sem `state`, monta as dependências de produção (toca `data/app.sqlite` real).

    Produção usa `uvicorn aml_guardian.api.app:create_app --factory` — nunca um `app` de módulo nível superior,
    para que importar este arquivo em teste não crie `data/app.sqlite` nem GraphDeps reais como efeito colateral.
    """
    app = FastAPI(title="AML Guardian API")
    app.state.aml = state or _default_app_state()
    register_exception_handlers(app)
    app.include_router(router)
    return app
