"""Checkpoint SQLite do grafo (T1.10, AGENTS.md §1): salvo pelo `langgraph-checkpoint-sqlite` após cada nó.

Arquivo próprio (`data/graph_checkpoints.sqlite`), separado de `data/app.sqlite`: o schema do checkpointer é do
LangGraph, não da auditoria DT-12 (T1.1). `SqliteSaver.from_conn_string` é um gerenciador de contexto — o grafo
só pode ser invocado dentro do `with`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

DEFAULT_CHECKPOINT_PATH = Path(__file__).resolve().parents[3] / "data" / "graph_checkpoints.sqlite"


@contextmanager
def sqlite_checkpointer(db_path: Path | str | None = None) -> Iterator[SqliteSaver]:
    """Abre o checkpointer SQLite; `":memory:"` ou um `Path` de teste evitam tocar `data/graph_checkpoints.sqlite`."""
    if db_path is None:
        DEFAULT_CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn_string = str(DEFAULT_CHECKPOINT_PATH)
    else:
        conn_string = str(db_path)
    with SqliteSaver.from_conn_string(conn_string) as saver:
        yield saver
