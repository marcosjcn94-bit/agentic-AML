"""Repositório de DT-05 (T1.11, RF-09, RF-10): upsert e leitura de `alert_records`, sem dado pessoal."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from aml_guardian.contracts.ingestion import AlertRecord
from aml_guardian.persistence.db import get_connection, get_db_path


def save_alert_record(record: AlertRecord, db_path: Path | None = None) -> None:
    """Insere ou atualiza o registro do alerta (chave `alert_id`)."""
    conn = get_connection(db_path or get_db_path())
    try:
        conn.execute(
            """
            INSERT INTO alert_records (
                alert_id, state, triage_level, selected_at, prazo_interno,
                prazo_regulatorio_analise, failure_reason, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(alert_id) DO UPDATE SET
                state = excluded.state,
                triage_level = excluded.triage_level,
                prazo_interno = excluded.prazo_interno,
                prazo_regulatorio_analise = excluded.prazo_regulatorio_analise,
                failure_reason = excluded.failure_reason,
                updated_at = excluded.updated_at
            """,
            (
                str(record.alert_id),
                record.state.value,
                record.triage_level.value if record.triage_level else None,
                record.selected_at.isoformat(),
                record.prazo_interno.isoformat() if record.prazo_interno else None,
                record.prazo_regulatorio_analise.isoformat() if record.prazo_regulatorio_analise else None,
                record.failure_reason,
                record.created_at.isoformat(),
                record.updated_at.isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_alert_record(alert_id: UUID, db_path: Path | None = None) -> AlertRecord | None:
    """Devolve o registro do alerta, ou `None` se `alert_id` não existir (404 lógico da API-03)."""
    conn = get_connection(db_path or get_db_path())
    try:
        row = conn.execute("SELECT * FROM alert_records WHERE alert_id = ?", (str(alert_id),)).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return AlertRecord.model_validate(dict(row))
