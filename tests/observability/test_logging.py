import json
import logging

from aml_guardian.observability.logging import JsonFormatter, configure_logging, log_event


def test_log_event_descarta_campos_fora_da_allowlist(capsys) -> None:
    configure_logging()
    log_event(
        "ALERT_RECEIVED",
        trace_id="trace-sintetico",
        pii="CPF-REAL-NUNCA-DEVE-APARECER",
    )

    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {"timestamp", "level", "event", "trace_id"}
    assert "CPF-REAL-NUNCA-DEVE-APARECER" not in json.dumps(payload)


def test_formatter_mantem_schema_json_controlado() -> None:
    record = logging.LogRecord("aml_guardian", logging.INFO, __file__, 1, "evento", (), None)
    record.event = "ALERT_RECEIVED"
    record.trace_id = "trace-sintetico"

    payload = json.loads(JsonFormatter().format(record))

    assert set(payload) == {"timestamp", "level", "event", "trace_id"}
