"""SQLite WAL database initialization and connection management."""

import sqlite3
from collections.abc import Generator
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent.parent / "data" / "app.sqlite"


def get_db_path() -> Path:
    """Get the database path, creating parent directories if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return DB_PATH


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Get a SQLite connection with WAL mode enabled."""
    if db_path is None:
        db_path = get_db_path()

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path | None = None) -> None:
    """Initialize the database with audit trail table."""
    if db_path is None:
        db_path = get_db_path()

    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()

        # Create audit events table (DT-12)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                event_key TEXT NOT NULL UNIQUE,
                occurred_at TEXT NOT NULL,
                alert_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor TEXT NOT NULL,
                state_from TEXT,
                state_to TEXT,
                model_id TEXT,
                prompt_sha256 TEXT,
                rules_version TEXT,
                corpus_version TEXT,
                mapping_version TEXT,
                prompt_version TEXT,
                tokens_in INTEGER NOT NULL DEFAULT 0,
                tokens_out INTEGER NOT NULL DEFAULT 0,
                latency_ms INTEGER NOT NULL DEFAULT 0,
                prev_hash TEXT,
                hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        # Create alert records table (DT-05)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alert_records (
                alert_id TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                triage_level TEXT,
                selected_at TEXT NOT NULL,
                prazo_interno TEXT,
                prazo_regulatorio_analise TEXT,
                failure_reason TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alert_ingestions (
                alert_id TEXT PRIMARY KEY,
                payload_sha256 TEXT NOT NULL
            )
        """)

        # Create trigger to prevent UPDATE on audit_events
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS prevent_audit_update
            BEFORE UPDATE ON audit_events
            BEGIN
                SELECT RAISE(ABORT, 'audit_events table is append-only');
            END
        """)

        # Create trigger to prevent DELETE on audit_events
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS prevent_audit_delete
            BEFORE DELETE ON audit_events
            BEGIN
                SELECT RAISE(ABORT, 'audit_events table is append-only');
            END
        """)

        conn.commit()
    finally:
        conn.close()


def connect_db(db_path: Path | None = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for database connections."""
    if db_path is None:
        db_path = get_db_path()

    conn = get_connection(db_path)
    try:
        yield conn
    finally:
        conn.close()
