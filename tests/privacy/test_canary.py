"""Canário RNF-05 inicial (T1.12): valores sintéticos marcados não aparecem em três destinos.

Os três destinos do canário: (1) prompts capturados no callback do LiteLLM antes da chamada ao modelo — a
produção nunca grava prompt nem resposta (RF-11); aqui o teste espia `litellm.completion` só para provar a
ausência, sem alterar `investigation/litellm_client.py`; (2) `data/app.sqlite` (DT-05 e DT-12, que só admitem
token/hash, nunca PII); (3) logs de aplicação, cobertos pelo formatter JSON
allow-listado em `tests/observability/test_logging.py`.
"""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

import aml_guardian.investigation.litellm_client as litellm_client_module
from aml_guardian.api.app import create_app
from aml_guardian.api.health import HealthDeps
from aml_guardian.api.state import AppState
from aml_guardian.config.triage import load_triage_rules
from aml_guardian.graph.deps import GraphDeps
from aml_guardian.norms.normalize import text_sha256
from aml_guardian.persistence.db import get_connection, init_db
from aml_guardian.sourcedata.documentos import gera_cpf

BASE = datetime(2026, 9, 1, tzinfo=UTC)
TEXTO_NORMATIVO = "Fragmentação de depósitos em espécie para dissimular o valor total da movimentação."
MARCADOR_NOME = "Ciclano Canario Sintetico"
MARCADOR_CPF = gera_cpf(random.Random(31415926))
MARCADOR_CONTA_REMETENTE = "9999900001"
MARCADOR_CONTA_DESTINO = "9999900002"

TOKENS = {
    "API_TOKEN_SISTEMA": "token-sistema",
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


def _payload_marcado() -> dict:
    """3 transações de fragmentação com CPF, nome e contas marcados (RF-03 dispara `TriageLevel.INVESTIGAR`)."""
    cfg = load_triage_rules().detectores_criticos.fragmentacao
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
            "sender_account": MARCADOR_CONTA_REMETENTE,
            "receiver_account": MARCADOR_CONTA_DESTINO,
        }
        for i in range(cfg.min_transacoes)
    ]
    fim = (inicio + timedelta(days=cfg.janela_dias)).isoformat()
    return {
        "alert_id": str(uuid4()),
        "source_rule_id": "LEG-TEST-CANARIO-01",
        "selected_at": inicio.isoformat(),
        "occurrence_window": {"start": inicio.isoformat(), "end": fim},
        "sender_account": MARCADOR_CONTA_REMETENTE,
        "sender_customer": {"name": MARCADOR_NOME, "cpf_cnpj": MARCADOR_CPF},
        "transactions": transacoes,
    }


def _dump_texto_sqlite(db_path: Path) -> str:
    """Concatena todo texto de `audit_events` (DT-12) e `alert_records` (DT-05) para a busca do canário."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        pedacos: list[str] = []
        for tabela in ("audit_events", "alert_records"):  # nomes fixos de `persistence/db.py`, não input externo
            cursor.execute(f"SELECT * FROM {tabela}")  # noqa: S608 - nome de tabela é literal fixo, não input
            for linha in cursor.fetchall():
                pedacos.append(" ".join(str(valor) for valor in linha if valor is not None))
        return " ".join(pedacos)
    finally:
        conn.close()


def test_valores_marcados_nao_aparecem_em_prompt_nem_em_app_sqlite(tmp_path, monkeypatch):
    for env_var, token in TOKENS.items():
        monkeypatch.setenv(env_var, token)

    prompts_capturados: list[str] = []
    original_completion = litellm_client_module.litellm.completion

    def _completion_espia(*args, **kwargs):
        for mensagem in kwargs.get("messages", []):
            prompts_capturados.append(str(mensagem.get("content", "")))
        return original_completion(*args, **kwargs)

    monkeypatch.setattr(litellm_client_module.litellm, "completion", _completion_espia)

    db_path = tmp_path / "app.sqlite"
    init_db(db_path)
    mock_resposta = json.dumps({"t": "Structuring", "c": 0.82, "r": "COMUNICAR", "e": [3]})
    state = AppState(
        graph_deps=GraphDeps(
            corpus_version="corpus-v1",
            history_fetcher=_historico_180d,
            restriction_checker=_mcp02_limpo,
            searcher=_fake_searcher(),
            passage_getter=_fake_getter(),
            model_overrides={"mock_response": mock_resposta},
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
    client = TestClient(create_app(state=state))

    payload = _payload_marcado()
    resp = client.post("/alerts", json=payload, headers=_bearer("API_TOKEN_SISTEMA"))
    assert resp.status_code == 202
    assert resp.json()["state"] == "DRAFT_READY"

    assert prompts_capturados, "nenhum prompt foi capturado — o canário não testou nada"

    marcadores = [MARCADOR_NOME, MARCADOR_CPF, MARCADOR_CONTA_REMETENTE, MARCADOR_CONTA_DESTINO]
    for marcador in marcadores:
        for prompt in prompts_capturados:
            assert marcador not in prompt, f"{marcador!r} vazou no prompt capturado do LiteLLM"

    conteudo_sqlite = _dump_texto_sqlite(db_path)
    for marcador in marcadores:
        assert marcador not in conteudo_sqlite, f"{marcador!r} vazou em data/app.sqlite"

    # O terceiro destino (logs) possui canário dedicado em tests/observability.
