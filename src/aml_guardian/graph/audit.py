"""Evento DT-12 por nó do grafo (T1.10, AGENTS.md §1, RF-11): `event_key = alert_id + node + attempt`.

Idempotente pela `UNIQUE(event_key)` já criada em `persistence/db.py` (T1.1): reexecutar o mesmo nó na mesma
tentativa não duplica o evento — `add_event` propaga o erro de `UNIQUE` da mesma forma que qualquer outra falha
de auditoria, tratada como best-effort pelos nós (mesmo padrão de `investigation/runner.py::_registrar_evento`).
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from aml_guardian.audit.chain import add_event
from aml_guardian.contracts.envelope import Node
from aml_guardian.contracts.runtime import AlertState, Role


def record_node_event(
    alert_id: UUID,
    node: Node,
    attempt: int,
    event_type: str,
    state_from: AlertState | None = None,
    state_to: AlertState | None = None,
    db_path: Path | None = None,
) -> None:
    """Registra evento regulatório; falha propaga e força o handoff seguro.

    `db_path` vem de `GraphDeps.db_path` (T1.12): sem ele, todo evento cairia sempre no `data/app.sqlite`
    de produção, inclusive durante teste — o mesmo db_path que `AppState`/`save_alert_record` já usam (T1.11).
    """
    add_event(
        alert_id=str(alert_id),
        event_type=event_type,
        event_key=f"{alert_id}_{node.value}_{attempt}",
        actor=Role.SISTEMA,
        state_from=state_from,
        state_to=state_to,
        db_path=db_path,
    )
