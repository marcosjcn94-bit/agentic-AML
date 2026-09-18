"""Persistência dos prazos do dossiê em DT-05 (`alert_records`, tabela da T1.1) — T1.9, RF-09.

Reusa `aml_guardian.persistence.db` (conexão WAL e schema já criados na T1.1); este módulo só faz upsert/leitura
dos campos de prazo. `state` é responsabilidade da máquina de estados (RF-10, T1.10) — aqui é só persistido junto,
nunca inferido.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from aml_guardian.contracts.ingestion import AlertState
from aml_guardian.contracts.pipeline import DossierDeadlines
from aml_guardian.persistence.db import get_connection, get_db_path


def save_deadlines(
    alert_id: UUID,
    state: AlertState,
    deadlines: DossierDeadlines,
    db_path: Path | None = None,
) -> None:
    """Grava (insere ou atualiza) `prazo_interno` e `prazo_regulatorio_analise` de `alert_id` em DT-05."""
    conn = get_connection(db_path or get_db_path())
    try:
        agora = datetime.now(UTC).isoformat()
        conn.execute(
            """
            INSERT INTO alert_records (
                alert_id, state, selected_at, prazo_interno, prazo_regulatorio_analise, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(alert_id) DO UPDATE SET
                state = excluded.state,
                selected_at = excluded.selected_at,
                prazo_interno = excluded.prazo_interno,
                prazo_regulatorio_analise = excluded.prazo_regulatorio_analise,
                updated_at = excluded.updated_at
            """,
            (
                str(alert_id),
                state.value,
                deadlines.selecao_em.isoformat(),
                deadlines.prazo_interno.isoformat(),
                deadlines.prazo_regulatorio_analise.isoformat(),
                agora,
                agora,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_deadlines(alert_id: UUID, db_path: Path | None = None) -> DossierDeadlines | None:
    """Lê os prazos persistidos de `alert_id`; `None` se o alerta não tem registro ou prazo ainda não calculado."""
    conn = get_connection(db_path or get_db_path())
    try:
        row = conn.execute(
            "SELECT selected_at, prazo_interno, prazo_regulatorio_analise FROM alert_records WHERE alert_id = ?",
            (str(alert_id),),
        ).fetchone()
        if row is None or row["prazo_interno"] is None:
            return None
        return DossierDeadlines(
            selecao_em=datetime.fromisoformat(row["selected_at"]),
            prazo_interno=datetime.fromisoformat(row["prazo_interno"]),
            prazo_regulatorio_analise=datetime.fromisoformat(row["prazo_regulatorio_analise"]),
        )
    finally:
        conn.close()
