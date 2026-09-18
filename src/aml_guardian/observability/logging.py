"""Logging JSON mínimo, com allow-list de campos e sem payloads."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "event": getattr(record, "event", record.getMessage()),
            "trace_id": getattr(record, "trace_id", "system"),
        }
        return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def configure_logging() -> None:
    """Instala um único handler JSON no logger da aplicação."""
    logger = logging.getLogger("aml_guardian")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.propagate = False


def log_event(event: str, *, trace_id: str = "system", level: int = logging.INFO, **_: Any) -> None:
    """Emite somente campos permitidos; argumentos extras são deliberadamente descartados."""
    logging.getLogger("aml_guardian").log(level, event, extra={"event": event, "trace_id": trace_id})
