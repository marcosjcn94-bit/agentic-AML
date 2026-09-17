"""Hash-chain audit trail implementation."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from aml_guardian.contracts.runtime import AuditEvent, Role
from aml_guardian.persistence.db import get_connection, get_db_path


class AuditChain:
    """Manages append-only audit trail with SHA-256 hash chain."""

    def __init__(self, db_path: Path | None = None):
        """Initialize audit chain with database path."""
        self.db_path = db_path or get_db_path()

    def add_event(
        self,
        alert_id: str | UUID,
        event_type: str,
        event_key: str,
        actor: Role,
        state_from: str | None = None,
        state_to: str | None = None,
        model_id: str | None = None,
        prompt_sha256: str | None = None,
        prompt_version: str | None = None,
        rules_version: str | None = None,
        corpus_version: str | None = None,
        mapping_version: str | None = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
        latency_ms: int = 0,
    ) -> AuditEvent:
        """Add an event to the audit trail and return the created AuditEvent."""
        # Ensure alert_id is a UUID
        if isinstance(alert_id, str):
            alert_id_uuid = UUID(alert_id)
        else:
            alert_id_uuid = alert_id

        alert_id_str = str(alert_id_uuid)

        conn = get_connection(self.db_path)
        cursor = conn.cursor()

        # Get the latest event to compute prev_hash
        cursor.execute("SELECT seq, hash FROM audit_events ORDER BY seq DESC LIMIT 1")
        last_event = cursor.fetchone()
        seq = (last_event[0] + 1) if last_event else 1
        prev_hash = last_event[1] if last_event else None

        occurred_at = datetime.now(UTC)
        now_str = occurred_at.isoformat()

        # Create the event data for hashing (exclude hash field itself)
        event_data = {
            "seq": seq,
            "event_key": event_key,
            "occurred_at": occurred_at.isoformat(),
            "alert_id": alert_id_str,
            "event_type": event_type,
            "actor": actor.value,
            "state_from": state_from,
            "state_to": state_to,
            "model_id": model_id,
            "prompt_sha256": prompt_sha256,
            "rules_version": rules_version,
            "corpus_version": corpus_version,
            "mapping_version": mapping_version,
            "prompt_version": prompt_version,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "latency_ms": latency_ms,
            "prev_hash": prev_hash,
        }

        # Canonical JSON for hashing (sorted keys, no whitespace)
        json_str = json.dumps(event_data, sort_keys=True, separators=(",", ":"))
        event_hash = hashlib.sha256(json_str.encode()).hexdigest()

        # Insert into database
        cursor.execute(
            """
            INSERT INTO audit_events (
                seq, event_key, occurred_at, alert_id, event_type, actor,
                state_from, state_to, model_id, prompt_sha256, rules_version,
                corpus_version, mapping_version, prompt_version,
                tokens_in, tokens_out, latency_ms, prev_hash, hash, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                seq,
                event_key,
                now_str,
                alert_id_str,
                event_type,
                actor.value,
                state_from,
                state_to,
                model_id,
                prompt_sha256,
                rules_version,
                corpus_version,
                mapping_version,
                prompt_version,
                tokens_in,
                tokens_out,
                latency_ms,
                prev_hash,
                event_hash,
                now_str,
            ),
        )
        conn.commit()
        conn.close()

        # Return as AuditEvent contract
        return AuditEvent(
            seq=seq,
            event_key=event_key,
            occurred_at=occurred_at,
            alert_id=alert_id_uuid,
            event_type=event_type,
            actor=actor,
            state_from=state_from,
            state_to=state_to,
            model_id=model_id,
            prompt_sha256=prompt_sha256,
            rules_version=rules_version,
            corpus_version=corpus_version,
            mapping_version=mapping_version,
            prompt_version=prompt_version,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            prev_hash=prev_hash,
            hash=event_hash,
        )

    def get_events(self, alert_id: str | None = None) -> list[AuditEvent]:
        """Retrieve events from the audit trail, optionally filtered by alert_id."""
        conn = get_connection(self.db_path)
        cursor = conn.cursor()

        if alert_id:
            cursor.execute("SELECT * FROM audit_events WHERE alert_id = ? ORDER BY seq", (alert_id,))
        else:
            cursor.execute("SELECT * FROM audit_events ORDER BY seq")

        rows = cursor.fetchall()
        conn.close()

        events = []
        for row in rows:
            events.append(
                AuditEvent(
                    seq=row[0],
                    event_key=row[1],
                    occurred_at=datetime.fromisoformat(row[2]).replace(tzinfo=UTC),
                    alert_id=row[3],
                    event_type=row[4],
                    actor=Role(row[5]),
                    state_from=row[6],
                    state_to=row[7],
                    model_id=row[8],
                    prompt_sha256=row[9],
                    rules_version=row[10],
                    corpus_version=row[11],
                    mapping_version=row[12],
                    prompt_version=row[13],
                    tokens_in=row[14],
                    tokens_out=row[15],
                    latency_ms=row[16],
                    prev_hash=row[17],
                    hash=row[18],
                )
            )
        return events

    def verify_chain(self) -> bool:
        """Verify the integrity of the entire hash chain."""
        conn = get_connection(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM audit_events ORDER BY seq")
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return True

        for row in rows:
            seq = row[0]
            prev_hash = row[17]
            stored_hash = row[18]

            # First event must have prev_hash = None
            if seq == 1 and prev_hash is not None:
                return False

            # Recalculate hash
            event_data = {
                "seq": seq,
                "event_key": row[1],
                "occurred_at": row[2],
                "alert_id": row[3],
                "event_type": row[4],
                "actor": row[5],
                "state_from": row[6],
                "state_to": row[7],
                "model_id": row[8],
                "prompt_sha256": row[9],
                "rules_version": row[10],
                "corpus_version": row[11],
                "mapping_version": row[12],
                "prompt_version": row[13],
                "tokens_in": row[14],
                "tokens_out": row[15],
                "latency_ms": row[16],
                "prev_hash": prev_hash,
            }
            json_str = json.dumps(event_data, sort_keys=True, separators=(",", ":"))
            calculated_hash = hashlib.sha256(json_str.encode()).hexdigest()

            if calculated_hash != stored_hash:
                return False

        return True

    def recalculate_chain(self) -> bool:
        """Recalculate the entire chain (should only be used if chain is verified first)."""
        if not self.verify_chain():
            return False

        # This is informational only; the chain is already correct
        # In a real scenario, you might use this to rebuild after verification
        return True


def add_event(
    alert_id: str,
    event_type: str,
    event_key: str,
    actor: Role,
    state_from: str | None = None,
    state_to: str | None = None,
    model_id: str | None = None,
    prompt_sha256: str | None = None,
    prompt_version: str | None = None,
    rules_version: str | None = None,
    corpus_version: str | None = None,
    mapping_version: str | None = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
    latency_ms: int = 0,
    db_path: Path | None = None,
) -> AuditEvent:
    """Convenience function to add an event to the audit trail."""
    chain = AuditChain(db_path)
    return chain.add_event(
        alert_id=alert_id,
        event_type=event_type,
        event_key=event_key,
        actor=actor,
        state_from=state_from,
        state_to=state_to,
        model_id=model_id,
        prompt_sha256=prompt_sha256,
        prompt_version=prompt_version,
        rules_version=rules_version,
        corpus_version=corpus_version,
        mapping_version=mapping_version,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=latency_ms,
    )


def recalculate_chain(db_path: Path | None = None) -> bool:
    """Convenience function to recalculate the chain."""
    chain = AuditChain(db_path)
    return chain.recalculate_chain()
