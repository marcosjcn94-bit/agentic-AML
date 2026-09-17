"""Estado injetável da aplicação FastAPI (T1.11): dependências do grafo, checkpoint, banco e `/health`.

`app.state.aml` guarda um único `AppState`; testes constroem o seu próprio com `GraphDeps`/`HealthDeps` falsos,
no mesmo espírito das dependências injetáveis do grafo (T1.10, `graph/deps.py`).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from aml_guardian.api.health import HealthDeps
from aml_guardian.graph.deps import GraphDeps


@dataclass
class AppState:
    graph_deps: GraphDeps
    health_deps: HealthDeps
    db_path: Path | None = None
    checkpoint_path: Path | str | None = None
