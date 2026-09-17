"""Persistent storage layer for AML Guardian (RF-10, RF-11).

This module manages SQLite WAL database with audit trail support.
"""

__all__ = ["get_db_path", "init_db", "get_connection"]
