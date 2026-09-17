"""Audit trail with hash-chain integrity (DT-12, RF-10, RF-11)."""

from .chain import AuditChain, add_event, recalculate_chain

__all__ = ["AuditChain", "add_event", "recalculate_chain"]
