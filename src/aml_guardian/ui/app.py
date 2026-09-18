"""Fila, reidentificação e decisão humana, exclusivamente via API REST."""

from __future__ import annotations

import os

import streamlit as st

from aml_guardian.ui.api_client import ApiClient, ApiClientError
from aml_guardian.ui.session import select_alert


def main() -> None:
    st.set_page_config(page_title="AML Guardian", layout="wide")
    api_url = os.getenv("AML_API_URL", "http://localhost:8000")
    analyst = ApiClient(api_url, os.getenv("API_TOKEN_ANALISTA", ""))
    officer = ApiClient(api_url, os.getenv("API_TOKEN_COMPLIANCE_OFFICER", ""))
    st.title("AML Guardian")
    try:
        state_filter = st.sidebar.selectbox(
            "Estado",
            [None, "DRAFT_READY", "SUBMITTED", "APPROVED", "RETURNED"],
            format_func=lambda value: value or "Todos",
        )
        alerts = analyst.list_alerts(state=state_filter, em_risco=st.sidebar.checkbox("Somente em risco"))
    except ApiClientError as exc:
        st.error(f"API indisponível ({exc.status_code})")
        return
    if not alerts:
        st.info("Nenhum alerta na fila.")
        return
    selected = st.selectbox("Alerta", alerts, format_func=lambda item: item["alert_id"])
    select_alert(st.session_state, selected["alert_id"])
    alert_id = selected["alert_id"]
    try:
        dossier = analyst.dossier(alert_id)
    except ApiClientError as exc:
        st.error(f"Dossiê indisponível ({exc.status_code})")
        return

    st.subheader("Dossiê mascarado")
    st.json(dossier)
    ai_fields = dossier.get("ai_generated_fields", [])
    if ai_fields:
        st.caption("Gerado por IA: " + ", ".join(ai_fields))

    if st.button("Reidentificar", type="secondary"):
        try:
            st.session_state["reidentified"] = analyst.reidentify(alert_id)["tokens"]
        except ApiClientError as exc:
            st.error(f"Reidentificação indisponível ({exc.status_code})")
    if values := st.session_state.get("reidentified"):
        st.warning("Dados reidentificados: uso restrito ao analista autorizado.")
        st.json(values)

    record_state = selected.get("state")
    if record_state == "DRAFT_READY" and st.button("Submeter para decisão"):
        try:
            analyst.submit(alert_id)
            st.success("Dossiê submetido.")
        except ApiClientError as exc:
            st.error(f"Falha ao submeter ({exc.status_code})")

    if record_state == "SUBMITTED":
        decision = st.selectbox("Decisão", ["COMUNICAR", "ARQUIVAR", "DEVOLVER"])
        justification = st.text_area("Justificativa", help="Mínimo de 50 caracteres.")
        if st.button("Registrar decisão"):
            if len(justification.strip()) < 50:
                st.warning("A justificativa deve ter ao menos 50 caracteres.")
            else:
                try:
                    officer.approve(alert_id, decision, justification)
                    st.success("Decisão registrada.")
                except ApiClientError as exc:
                    st.error(f"Falha ao decidir ({exc.status_code})")


if __name__ == "__main__":
    main()
