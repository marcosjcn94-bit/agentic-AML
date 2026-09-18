"""Estado volátil da UI para valores reidentificados."""

from __future__ import annotations


def clear_reidentified(session_state: dict[str, object]) -> None:
    session_state.pop("reidentified", None)
    session_state.pop("selected_alert_id", None)


def select_alert(session_state: dict[str, object], alert_id: str) -> None:
    if session_state.get("selected_alert_id") != alert_id:
        clear_reidentified(session_state)
        session_state["selected_alert_id"] = alert_id
