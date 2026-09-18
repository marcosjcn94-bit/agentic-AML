"""Testes da API base (T1.11, API-01, API-03, API-09): papel por Bearer, códigos HTTP, `/health`."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from aml_guardian.api.app import create_app
from aml_guardian.api.health import HealthDeps
from aml_guardian.api.state import AppState
from aml_guardian.graph.deps import GraphDeps
from aml_guardian.persistence.db import init_db
from aml_guardian.sourcedata.documentos import gera_cpf

BASE = datetime(2026, 9, 1, tzinfo=UTC)
VALID_CPF = gera_cpf(random.Random(20260917))

TOKENS = {
    "API_TOKEN_SISTEMA": "token-sistema",
    "API_TOKEN_ANALISTA": "token-analista",
    "API_TOKEN_COMPLIANCE_OFFICER": "token-officer",
}


def _bearer(env_var: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKENS[env_var]}"}


def _alert_payload(*, alert_id=None, valor: str = "150.00") -> dict[str, object]:
    alert_id = alert_id or uuid4()
    inicio = BASE.isoformat()
    fim = (BASE + timedelta(days=1)).isoformat()
    return {
        "alert_id": str(alert_id),
        "source_rule_id": "LEG-TEST-01",
        "selected_at": inicio,
        "occurrence_window": {"start": inicio, "end": fim},
        "sender_account": "1111122222",
        "sender_customer": {"name": "Fulano de Tal", "cpf_cnpj": VALID_CPF},
        "transactions": [
            {
                "transaction_id": "tx-0001",
                "timestamp": inicio,
                "amount_brl": valor,
                "payment_type": "PIX",
                "sender_location": "BR",
                "receiver_location": "BR",
                "currency_sent": "BRL",
                "currency_received": "BRL",
                "sender_account": "1111122222",
                "receiver_account": "3333344444",
            }
        ],
    }


def _mcp02_limpo(customer_id: str, cpf_cnpj_token: str | None = None) -> dict:
    return {
        "status": "success",
        "customer_id": customer_id,
        "pep": "nao",
        "ceis": "nao",
        "cnep": "nao",
        "list_version": "v1",
    }


def _historico_180d(customer_id: str, window_days: int) -> dict:
    return {"status": "success", "customer_id": customer_id, "total_amount": "1000.00", "transaction_count": 1}


@pytest.fixture
def client(tmp_path, monkeypatch):
    for env_var, token in TOKENS.items():
        monkeypatch.setenv(env_var, token)

    db_path = tmp_path / "app.sqlite"
    init_db(db_path)
    state = AppState(
        graph_deps=GraphDeps(
            corpus_version="corpus-v1",
            history_fetcher=_historico_180d,
            restriction_checker=_mcp02_limpo,
        ),
        health_deps=HealthDeps(
            sqlite_checker=lambda: True,
            chroma_checker=lambda: True,
            ollama_checker=lambda: True,
            corpus_version_getter=lambda: "corpus-v1",
        ),
        db_path=db_path,
        checkpoint_path=tmp_path / "checkpoints.sqlite",
    )
    return TestClient(create_app(state=state))


class TestPostAlertsAceite:
    def test_alerta_sem_detector_critico_chega_a_draft_ready(self, client):
        resp = client.post("/alerts", json=_alert_payload(), headers=_bearer("API_TOKEN_SISTEMA"))
        assert resp.status_code == 202
        body = resp.json()
        assert body["state"] == "DRAFT_READY"

    def test_alert_id_repetido_e_409(self, client):
        payload = _alert_payload()
        client.post("/alerts", json=payload, headers=_bearer("API_TOKEN_SISTEMA"))
        resp = client.post("/alerts", json=payload, headers=_bearer("API_TOKEN_SISTEMA"))
        assert resp.status_code == 409


class TestAutenticacaoPorPapel:
    def test_sem_token_e_401(self, client):
        resp = client.post("/alerts", json=_alert_payload())
        assert resp.status_code == 401

    def test_token_invalido_e_401(self, client):
        resp = client.post("/alerts", json=_alert_payload(), headers={"Authorization": "Bearer lixo"})
        assert resp.status_code == 401

    def test_papel_errado_e_403(self, client):
        resp = client.post("/alerts", json=_alert_payload(), headers=_bearer("API_TOKEN_ANALISTA"))
        assert resp.status_code == 403

    def test_analista_le_alerta_mas_sistema_nao(self, client):
        payload = _alert_payload()
        client.post("/alerts", json=payload, headers=_bearer("API_TOKEN_SISTEMA"))
        ok = client.get(f"/alerts/{payload['alert_id']}", headers=_bearer("API_TOKEN_ANALISTA"))
        negado = client.get(f"/alerts/{payload['alert_id']}", headers=_bearer("API_TOKEN_SISTEMA"))
        assert ok.status_code == 200
        assert negado.status_code == 403


class TestNaoEncontrado:
    def test_alerta_desconhecido_e_404(self, client):
        resp = client.get(f"/alerts/{uuid4()}", headers=_bearer("API_TOKEN_ANALISTA"))
        assert resp.status_code == 404

    def test_dossie_desconhecido_e_404(self, client):
        resp = client.get(f"/dossiers/{uuid4()}", headers=_bearer("API_TOKEN_COMPLIANCE_OFFICER"))
        assert resp.status_code == 404

    def test_dossie_do_caminho_arquivamento_disponivel(self, client):
        payload = _alert_payload()
        client.post("/alerts", json=payload, headers=_bearer("API_TOKEN_SISTEMA"))
        resp = client.get(f"/dossiers/{payload['alert_id']}", headers=_bearer("API_TOKEN_COMPLIANCE_OFFICER"))
        assert resp.status_code == 200
        assert resp.json()["type"] == "ARQUIVAMENTO"


class TestValidacaoDePayload:
    def test_payload_invalido_e_422_sem_ecoar_valor(self, client):
        payload = _alert_payload(valor="-50.00")  # amount_brl exige > 0 (DT-02)
        resp = client.post("/alerts", json=payload, headers=_bearer("API_TOKEN_SISTEMA"))
        assert resp.status_code == 422
        assert "-50.00" not in resp.text


class TestHealth:
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_health_503_com_dependencia_fora(self, tmp_path, monkeypatch):
        for env_var, token in TOKENS.items():
            monkeypatch.setenv(env_var, token)
        db_path = tmp_path / "app.sqlite"
        init_db(db_path)
        state = AppState(
            graph_deps=GraphDeps(corpus_version="corpus-v1"),
            health_deps=HealthDeps(
                sqlite_checker=lambda: True,
                chroma_checker=lambda: True,
                ollama_checker=lambda: False,  # Ollama fora do ar
                corpus_version_getter=lambda: "corpus-v1",
            ),
            db_path=db_path,
        )
        resp = TestClient(create_app(state=state)).get("/health")
        assert resp.status_code == 503


class TestReidentificacao:
    def test_token_existente_devolve_valor_original(self, client):
        payload = _alert_payload()
        client.post("/alerts", json=payload, headers=_bearer("API_TOKEN_SISTEMA"))
        state: AppState = client.app.state.aml
        token = next(iter(state.vault.keys()))
        resp = client.get(f"/reidentify/{token}", headers=_bearer("API_TOKEN_ANALISTA"))
        assert resp.status_code == 200
        assert resp.json()["value"]

    def test_token_desconhecido_e_404(self, client):
        resp = client.get("/reidentify/CPF_99", headers=_bearer("API_TOKEN_COMPLIANCE_OFFICER"))
        assert resp.status_code == 404

    def test_sistema_nao_reidentifica(self, client):
        payload = _alert_payload()
        client.post("/alerts", json=payload, headers=_bearer("API_TOKEN_SISTEMA"))
        state: AppState = client.app.state.aml
        token = next(iter(state.vault.keys()))
        resp = client.get(f"/reidentify/{token}", headers=_bearer("API_TOKEN_SISTEMA"))
        assert resp.status_code == 403

    def test_dois_alertas_nao_colidem_no_vault_compartilhado(self, client):
        """Vault é 1/processo (ADR-012): CPF do 2º alerta não pode sobrescrever o token do 1º."""
        cpf_a = gera_cpf(random.Random(1))
        cpf_b = gera_cpf(random.Random(2))
        payload_a = _alert_payload()
        payload_a["sender_customer"]["cpf_cnpj"] = cpf_a
        payload_b = _alert_payload()
        payload_b["sender_customer"]["cpf_cnpj"] = cpf_b

        client.post("/alerts", json=payload_a, headers=_bearer("API_TOKEN_SISTEMA"))
        client.post("/alerts", json=payload_b, headers=_bearer("API_TOKEN_SISTEMA"))

        state: AppState = client.app.state.aml
        cpf_tokens = [t for t in state.vault.keys() if t.startswith("CPF_")]
        assert len(cpf_tokens) == 2
        valores = {state.vault.retrieve(t) for t in cpf_tokens}
        assert valores == {cpf_a, cpf_b}


class TestDecisaoDoComplianceOfficer:
    def test_aceite_muda_estado_para_approved(self, client):
        payload = _alert_payload()
        client.post("/alerts", json=payload, headers=_bearer("API_TOKEN_SISTEMA"))
        resp = client.post(
            f"/alerts/{payload['alert_id']}/decision",
            json={"decision": "ARQUIVAR", "justification": "Sem indício de lavagem após revisão manual completa."},
            headers=_bearer("API_TOKEN_COMPLIANCE_OFFICER"),
        )
        assert resp.status_code == 200
        assert resp.json()["state"] == "APPROVED"

    def test_analista_nao_decide(self, client):
        payload = _alert_payload()
        client.post("/alerts", json=payload, headers=_bearer("API_TOKEN_SISTEMA"))
        resp = client.post(
            f"/alerts/{payload['alert_id']}/decision",
            json={"decision": "ARQUIVAR", "justification": "Sem indício de lavagem após revisão manual completa."},
            headers=_bearer("API_TOKEN_ANALISTA"),
        )
        assert resp.status_code == 403

    def test_alerta_desconhecido_e_404(self, client):
        resp = client.post(
            f"/alerts/{uuid4()}/decision",
            json={"decision": "ARQUIVAR", "justification": "Sem indício de lavagem após revisão manual completa."},
            headers=_bearer("API_TOKEN_COMPLIANCE_OFFICER"),
        )
        assert resp.status_code == 404

    def test_decisao_repetida_e_409_sem_duplicar_evento(self, client):
        payload = _alert_payload()
        client.post("/alerts", json=payload, headers=_bearer("API_TOKEN_SISTEMA"))
        body = {"decision": "ARQUIVAR", "justification": "Sem indício de lavagem após revisão manual completa."}
        primeira = client.post(
            f"/alerts/{payload['alert_id']}/decision", json=body, headers=_bearer("API_TOKEN_COMPLIANCE_OFFICER")
        )
        segunda = client.post(
            f"/alerts/{payload['alert_id']}/decision", json=body, headers=_bearer("API_TOKEN_COMPLIANCE_OFFICER")
        )
        assert primeira.status_code == 200
        assert segunda.status_code == 409
