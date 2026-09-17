"""Tests for audit trail hash-chain (DT-12, RF-10, RF-11)."""

import sqlite3
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from aml_guardian.audit.chain import AuditChain, add_event, recalculate_chain
from aml_guardian.contracts.runtime import Role
from aml_guardian.persistence.db import init_db


@pytest.fixture
def temp_db():
    """Temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.sqlite"
        init_db(db_path)
        yield db_path


class TestAuditChain:
    """Tests for AuditChain class."""

    def test_add_single_event(self, temp_db):
        """Test adding a single event to the chain."""
        chain = AuditChain(temp_db)
        alert_id = str(uuid4())
        event_key = f"{alert_id}_TRIAGE_1"

        event = chain.add_event(
            alert_id=alert_id,
            event_type="ALERT_RECEIVED",
            event_key=event_key,
            actor=Role.SISTEMA,
            state_from="RECEIVED",
            state_to="SANITIZED",
        )

        assert event.seq == 1
        assert event.event_key == event_key
        assert event.prev_hash is None
        assert event.hash is not None
        assert len(event.hash) == 64  # SHA-256 hex

    def test_event_key_uniqueness(self, temp_db):
        """Test that duplicate event_key raises error (UNIQUE constraint)."""
        chain = AuditChain(temp_db)
        alert_id = str(uuid4())
        event_key = f"{alert_id}_TRIAGE_1"

        chain.add_event(
            alert_id=alert_id,
            event_type="ALERT_RECEIVED",
            event_key=event_key,
            actor=Role.SISTEMA,
        )

        # Try to add duplicate event_key
        with pytest.raises(sqlite3.IntegrityError):
            chain.add_event(
                alert_id=alert_id,
                event_type="TRIAGED",
                event_key=event_key,  # Same key
                actor=Role.SISTEMA,
            )

    def test_chain_linking(self, temp_db):
        """Test that events are properly chained with prev_hash."""
        chain = AuditChain(temp_db)
        alert_id = str(uuid4())

        # Add first event
        event1 = chain.add_event(
            alert_id=alert_id,
            event_type="ALERT_RECEIVED",
            event_key=f"{alert_id}_1",
            actor=Role.SISTEMA,
        )
        assert event1.prev_hash is None

        # Add second event
        event2 = chain.add_event(
            alert_id=alert_id,
            event_type="SANITIZED",
            event_key=f"{alert_id}_2",
            actor=Role.SISTEMA,
        )
        assert event2.seq == 2
        assert event2.prev_hash == event1.hash

        # Add third event
        event3 = chain.add_event(
            alert_id=alert_id,
            event_type="TRIAGED",
            event_key=f"{alert_id}_3",
            actor=Role.SISTEMA,
        )
        assert event3.seq == 3
        assert event3.prev_hash == event2.hash

    def test_no_update_on_events(self, temp_db):
        """Test that UPDATE is prevented by trigger."""

        chain = AuditChain(temp_db)
        alert_id = str(uuid4())

        chain.add_event(
            alert_id=alert_id,
            event_type="ALERT_RECEIVED",
            event_key=f"{alert_id}_1",
            actor=Role.SISTEMA,
        )

        # Try to update event
        from aml_guardian.persistence.db import get_connection

        conn = get_connection(temp_db)
        cursor = conn.cursor()
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute(
                "UPDATE audit_events SET event_type = ? WHERE seq = 1",
                ("MODIFIED",),
            )
            conn.commit()
        conn.close()

    def test_no_delete_on_events(self, temp_db):
        """Test that DELETE is prevented by trigger."""

        chain = AuditChain(temp_db)
        alert_id = str(uuid4())

        chain.add_event(
            alert_id=alert_id,
            event_type="ALERT_RECEIVED",
            event_key=f"{alert_id}_1",
            actor=Role.SISTEMA,
        )

        # Try to delete event
        from aml_guardian.persistence.db import get_connection

        conn = get_connection(temp_db)
        cursor = conn.cursor()
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute("DELETE FROM audit_events WHERE seq = 1")
            conn.commit()
        conn.close()

    def test_verify_chain(self, temp_db):
        """Test chain verification."""
        chain = AuditChain(temp_db)
        alert_id = str(uuid4())

        # Add several events
        for i in range(5):
            chain.add_event(
                alert_id=alert_id,
                event_type=f"EVENT_{i}",
                event_key=f"{alert_id}_{i}",
                actor=Role.SISTEMA,
            )

        assert chain.verify_chain() is True

    def test_get_events_by_alert(self, temp_db):
        """Test retrieving events by alert_id."""
        chain = AuditChain(temp_db)
        alert1_uuid = uuid4()
        alert1_str = str(alert1_uuid)
        alert2_uuid = uuid4()
        alert2_str = str(alert2_uuid)

        # Add events for both alerts
        for i in range(3):
            chain.add_event(
                alert_id=alert1_str,
                event_type=f"EVENT_{i}",
                event_key=f"{alert1_str}_{i}",
                actor=Role.SISTEMA,
            )
            chain.add_event(
                alert_id=alert2_str,
                event_type=f"EVENT_{i}",
                event_key=f"{alert2_str}_{i}",
                actor=Role.SISTEMA,
            )

        # Retrieve events for alert1
        alert1_events = chain.get_events(alert_id=alert1_str)
        assert len(alert1_events) == 3
        assert all(e.alert_id == alert1_uuid for e in alert1_events)

        # Retrieve events for alert2
        alert2_events = chain.get_events(alert_id=alert2_str)
        assert len(alert2_events) == 3
        assert all(e.alert_id == alert2_uuid for e in alert2_events)

    def test_event_without_pii(self, temp_db):
        """Test that events don't contain raw PII, only prompt_sha256."""
        chain = AuditChain(temp_db)
        alert_id = str(uuid4())
        prompt_hash = "a" * 64  # Valid SHA256 hash

        chain.add_event(
            alert_id=alert_id,
            event_type="INVESTIGATION",
            event_key=f"{alert_id}_inv",
            actor=Role.SISTEMA,
            model_id="ollama:llama3.1",
            prompt_sha256=prompt_hash,
            prompt_version="v1",
        )

        # Retrieve from DB and verify no raw data
        events = chain.get_events(alert_id=alert_id)
        assert events[0].prompt_sha256 == prompt_hash
        assert events[0].model_id == "ollama:llama3.1"

    def test_role_values(self, temp_db):
        """Test that different roles are properly stored."""
        chain = AuditChain(temp_db)
        alert_id = str(uuid4())

        # Add events with different roles
        event_sistema = chain.add_event(
            alert_id=alert_id,
            event_type="ALERT_RECEIVED",
            event_key=f"{alert_id}_sistema",
            actor=Role.SISTEMA,
        )

        event_analista = chain.add_event(
            alert_id=alert_id,
            event_type="REVIEWED",
            event_key=f"{alert_id}_analista",
            actor=Role.ANALISTA,
        )

        event_co = chain.add_event(
            alert_id=alert_id,
            event_type="APPROVED",
            event_key=f"{alert_id}_co",
            actor=Role.COMPLIANCE_OFFICER,
        )

        assert event_sistema.actor == Role.SISTEMA
        assert event_analista.actor == Role.ANALISTA
        assert event_co.actor == Role.COMPLIANCE_OFFICER

        # Verify retrieval
        events = chain.get_events(alert_id=alert_id)
        assert events[0].actor == Role.SISTEMA
        assert events[1].actor == Role.ANALISTA
        assert events[2].actor == Role.COMPLIANCE_OFFICER


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_add_event_function(self, temp_db):
        """Test convenience function for adding events."""
        alert_id_uuid = uuid4()
        alert_id_str = str(alert_id_uuid)
        event_key = f"{alert_id_str}_test"

        event = add_event(
            alert_id=alert_id_str,
            event_type="TEST",
            event_key=event_key,
            actor=Role.SISTEMA,
            db_path=temp_db,
        )

        assert event.seq == 1
        assert event.alert_id == alert_id_uuid

    def test_recalculate_chain_function(self, temp_db):
        """Test convenience function for recalculating chain."""
        chain = AuditChain(temp_db)
        alert_id = str(uuid4())

        chain.add_event(
            alert_id=alert_id,
            event_type="TEST",
            event_key=f"{alert_id}_1",
            actor=Role.SISTEMA,
        )

        result = recalculate_chain(temp_db)
        assert result is True
