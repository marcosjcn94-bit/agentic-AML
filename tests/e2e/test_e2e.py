"""E2E do M1 (T1.12, RF-01 a RF-11, RF-14, API-01, API-03): alerta via API até `DRAFT_READY`.

Só o modelo é simulado (`mock_response` do LiteLLM, como a T1.6); todo o resto — sanitizador, triagem, grafo,
auditoria — roda de verdade. O teste real com Ollama fica em `tests/investigation/test_investigation.py`,
marcado `-m ollama` (T1.6); este arquivo cobre o critério de saída do M1 com o caminho determinístico.
"""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from aml_guardian.api.app import create_app
from aml_guardian.api.health import HealthDeps
from aml_guardian.api.state import AppState
from aml_guardian.audit.chain import AuditChain
from aml_guardian.config.triage import load_triage_rules
from aml_guardian.graph.deps import GraphDeps
from aml_guardian.investigation.litellm_client import ContadorChamadas
from aml_guardian.norms.normalize import text_sha256
from aml_guardian.persistence.db import init_db
from aml_guardian.sourcedata.documentos import gera_cpf

RULES = load_triage_rules()
BASE = datetime(2026, 9, 1, tzinfo=UTC)
TEXTO_NORMATIVO = "Fragmentação de depósitos em espécie para dissimular o valor total da movimentação."
VALID_CPF = gera_cpf(random.Random(20260917))

TOKENS = {
    "API_TOKEN_SISTEMA": "token-sistema",
    "API_TOKEN_ANALISTA": "token-analista",
    "API_TOKEN_COMPLIANCE_OFFICER": "token-officer",
}


def _bearer(env_var: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKENS[env_var]}"}


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
    return {"status": "success", "customer_id": customer_id, "total_amount": "5000.00", "transaction_count": 5}


def _mock_investigation(t: str, c: float, r: str, e: list[int]) -> str:
    return json.dumps({"t": t, "c": c, "r": r, "e": e})


def _fake_searcher():
    def searcher(query: str, top_k: int, corpus_version: str) -> dict:
        return {
            "status": "success",
            "results": [{"chunk_id": "chunk-d", "article_ref": "CC4001/art1/i1/d", "score": 0.95}],
        }

    return searcher


def _fake_getter():
    sha = text_sha256(TEXTO_NORMATIVO)

    def getter(chunk_id: str, corpus_version: str) -> dict:
        return {"status": "success", "chunk_id": chunk_id, "text": TEXTO_NORMATIVO, "text_sha256": sha}

    return getter


def _payload_fragmentacao(
    cpf: str, *, sender_account: str = "1111122222", receiver_account: str = "3333344444"
) -> dict:
    """Payload cru (não sanitizado) que dispara o detector crítico de fragmentação (RF-03)."""
    cfg = RULES.detectores_criticos.fragmentacao
    inicio = BASE
    transacoes = [
        {
            "transaction_id": f"tx-{i:04d}",
            "timestamp": (inicio + timedelta(days=i)).isoformat(),
            "amount_brl": "500.00",
            "payment_type": "PIX",
            "sender_location": "BR",
            "receiver_location": "BR",
            "currency_sent": "BRL",
            "currency_received": "BRL",
            "sender_account": sender_account,
            "receiver_account": receiver_account,
        }
        for i in range(cfg.min_transacoes)
    ]
    fim = (inicio + timedelta(days=cfg.janela_dias)).isoformat()
    return {
        "alert_id": str(uuid4()),
        "source_rule_id": "LEG-TEST-E2E-01",
        "selected_at": inicio.isoformat(),
        "occurrence_window": {"start": inicio.isoformat(), "end": fim},
        "sender_account": sender_account,
        "sender_customer": {"name": "Fulano de Tal", "cpf_cnpj": cpf},
        "transactions": transacoes,
    }


def _payload_sem_detector(
    cpf: str, *, sender_account: str = "1111122222", receiver_account: str = "3333344444"
) -> dict:
    """Payload cru sem nenhum detector crítico disparado (`TriageLevel.PROPOR_ARQUIVAMENTO`)."""
    inicio = BASE
    return {
        "alert_id": str(uuid4()),
        "source_rule_id": "LEG-TEST-E2E-02",
        "selected_at": inicio.isoformat(),
        "occurrence_window": {"start": inicio.isoformat(), "end": (inicio + timedelta(days=1)).isoformat()},
        "sender_account": sender_account,
        "sender_customer": {"name": "Fulano de Tal", "cpf_cnpj": cpf},
        "transactions": [
            {
                "transaction_id": "tx-0001",
                "timestamp": inicio.isoformat(),
                "amount_brl": "150.00",
                "payment_type": "PIX",
                "sender_location": "BR",
                "receiver_location": "BR",
                "currency_sent": "BRL",
                "currency_received": "BRL",
                "sender_account": sender_account,
                "receiver_account": receiver_account,
            }
        ],
    }


def _make_app(tmp_path, monkeypatch, **graph_deps_kwargs) -> tuple[TestClient, AppState]:
    for env_var, token in TOKENS.items():
        monkeypatch.setenv(env_var, token)
    db_path = tmp_path / "app.sqlite"
    init_db(db_path)
    state = AppState(
        graph_deps=GraphDeps(corpus_version="corpus-v1", triage_rules=RULES, **graph_deps_kwargs),
        health_deps=HealthDeps(
            sqlite_checker=lambda: True,
            chroma_checker=lambda: True,
            ollama_checker=lambda: True,
            corpus_version_getter=lambda: "corpus-v1",
        ),
        db_path=db_path,
        checkpoint_path=tmp_path / "checkpoints.sqlite",
    )
    return TestClient(create_app(state=state)), state


class TestCaminhoInvestigarViaApi:
    def test_investigar_chega_a_draft_ready_com_citacao_verificada(self, tmp_path, monkeypatch):
        client, state = _make_app(
            tmp_path,
            monkeypatch,
            history_fetcher=_historico_180d,
            restriction_checker=_mcp02_limpo,
            searcher=_fake_searcher(),
            passage_getter=_fake_getter(),
            model_overrides={"mock_response": _mock_investigation("Structuring", 0.82, "COMUNICAR", [3])},
        )
        payload = _payload_fragmentacao(VALID_CPF)

        resp = client.post("/alerts", json=payload, headers=_bearer("API_TOKEN_SISTEMA"))
        assert resp.status_code == 202
        assert resp.json()["state"] == "DRAFT_READY"

        dossier = client.get(f"/dossiers/{payload['alert_id']}", headers=_bearer("API_TOKEN_COMPLIANCE_OFFICER"))
        assert dossier.status_code == 200
        body = dossier.json()
        assert body["type"] == "COS"
        assert len(body["citations"]) >= 1

        assert AuditChain(db_path=state.db_path).verify_chain()


class TestCaminhoArquivamentoViaApi:
    def test_propor_arquivamento_chega_a_draft_ready_sem_chamada_de_modelo(self, tmp_path, monkeypatch):
        contador = ContadorChamadas()
        client, state = _make_app(
            tmp_path,
            monkeypatch,
            history_fetcher=_historico_180d,
            restriction_checker=_mcp02_limpo,
            contador=contador,
        )
        payload = _payload_sem_detector(VALID_CPF)

        resp = client.post("/alerts", json=payload, headers=_bearer("API_TOKEN_SISTEMA"))
        assert resp.status_code == 202
        assert resp.json()["state"] == "DRAFT_READY"
        assert contador.chamadas == 0

        dossier = client.get(f"/dossiers/{payload['alert_id']}", headers=_bearer("API_TOKEN_COMPLIANCE_OFFICER"))
        assert dossier.status_code == 200
        assert dossier.json()["type"] == "ARQUIVAMENTO"

        assert AuditChain(db_path=state.db_path).verify_chain()
