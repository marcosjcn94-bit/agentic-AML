"""Tela mínima de fila e fluxo humano, consumindo exclusivamente a API REST."""

from __future__ import annotations

import os

import streamlit as st

from aml_guardian.ui.api_client import ApiClient, ApiClientError
from aml_guardian.ui.session import select_alert


def main() -> None:
    st.set_page_config(page_title="AML Guardian", layout="wide")
    client = ApiClient(os.getenv("AML_API_URL", "http://localhost:8000"), os.getenv("API_TOKEN_ANALISTA", ""))
    st.title("AML Guardian")
    try:
        alerts = client.list_alerts(em_risco=st.sidebar.checkbox("Somente em risco"))
    except ApiClientError as exc:
        st.error(f"API indisponível ({exc.status_code})")
        return
    if not alerts:
        st.info("Nenhum alerta na fila.")
        return
    selected = st.selectbox("Alerta", alerts, format_func=lambda item: item["alert_id"])
    select_alert(st.session_state, selected["alert_id"])
    st.json(client.dossier(selected["alert_id"]))


if __name__ == "__main__":
    main()
