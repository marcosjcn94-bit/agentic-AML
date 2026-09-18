"""Mede a latência do fluxo `INVESTIGAR` ponta a ponta (T1.13, RNF-03 informativa): via API-01, como em produção.

`mock_response` isola o determinismo do teste focado (`pytest -k evaluate`); a rodada real do M1 passa
`mock_response=None` para chamar o Ollama de verdade pelo LiteLLM (ADR-013), com o resto do grafo (MCP,
corpus) simulado pelos fakes de `eval/fixtures.py` — a latência medida isola o overhead do grafo em cima do
único nó LLM, que é o número que o ADR-013 já benchmarcou (15,0 s estimados).
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient

from aml_guardian.api.app import create_app
from aml_guardian.api.health import HealthDeps
from aml_guardian.api.state import AppState
from aml_guardian.audit.chain import AuditChain
from aml_guardian.config.triage import TriageRulesConfig, load_triage_rules
from aml_guardian.eval.fixtures import (
    gera_amostra,
    mcp01_historico_vazio,
    mcp02_sem_ocorrencia,
    norms_getter_fixo,
    norms_searcher_fixo,
)
from aml_guardian.graph.deps import GraphDeps
from aml_guardian.persistence.db import init_db

_TOKEN_SISTEMA = "eval-token-sistema"


@contextmanager
def _com_token_sistema() -> Iterator[None]:
    """Define `API_TOKEN_SISTEMA` para a duração da amostra e restaura o valor anterior ao sair.

    `os.environ` (não `monkeypatch`, que só existe em teste) porque `scripts/evaluate.py` roda fora do pytest.
    """
    anterior = os.environ.get("API_TOKEN_SISTEMA")
    os.environ["API_TOKEN_SISTEMA"] = _TOKEN_SISTEMA
    try:
        yield
    finally:
        if anterior is None:
            os.environ.pop("API_TOKEN_SISTEMA", None)
        else:
            os.environ["API_TOKEN_SISTEMA"] = anterior


@dataclass(frozen=True)
class AmostraLatencia:
    alert_id: str
    total_ms: float
    investigation_llm_ms: float | None
    model_id: str | None
    state_final: str


def _monta_cliente(tmp_dir: Path, rules: TriageRulesConfig, mock_response: str | None) -> tuple[TestClient, Path]:
    db_path = tmp_dir / "eval.sqlite"
    init_db(db_path)
    model_overrides: dict[str, object] = {}
    if mock_response is not None:
        model_overrides["mock_response"] = mock_response
    state = AppState(
        graph_deps=GraphDeps(
            corpus_version="eval-amostra-sintetica",
            triage_rules=rules,
            history_fetcher=mcp01_historico_vazio,
            restriction_checker=mcp02_sem_ocorrencia,
            searcher=norms_searcher_fixo(),
            passage_getter=norms_getter_fixo(),
            model_overrides=model_overrides,
        ),
        health_deps=HealthDeps(
            sqlite_checker=lambda: True,
            chroma_checker=lambda: True,
            ollama_checker=lambda: True,
            corpus_version_getter=lambda: "eval-amostra-sintetica",
        ),
        db_path=db_path,
        checkpoint_path=tmp_dir / "eval-checkpoints.sqlite",
    )
    return TestClient(create_app(state=state)), db_path


def _evento_model_called(db_path: Path, alert_id: str) -> tuple[float, str] | None:
    for evento in AuditChain(db_path=db_path).get_events(alert_id=alert_id):
        if evento.event_type == "MODEL_CALLED":
            return float(evento.latency_ms), evento.model_id or ""
    return None


def mede_fluxo_investigar(
    tamanho_amostra: int,
    tmp_dir: Path,
    *,
    mock_response: str | None,
) -> tuple[list[AmostraLatencia], bool]:
    """Roda `tamanho_amostra` alertas sintéticos `INVESTIGAR` via `POST /alerts`; devolve amostras + `valid`.

    Um único banco de auditoria para toda a amostra: `valid` é o resultado de `AuditChain.verify_chain()` ao
    final, cobrindo o gate "Integridade da auditoria" (API-08, `SPEC.md` §10) sobre esta execução.
    """
    rules = load_triage_rules()
    with _com_token_sistema():
        client, db_path = _monta_cliente(tmp_dir, rules, mock_response)
        amostras: list[AmostraLatencia] = []
        for payload in gera_amostra(tamanho_amostra, rules):
            inicio = time.perf_counter()
            resp = client.post("/alerts", json=payload, headers={"Authorization": f"Bearer {_TOKEN_SISTEMA}"})
            total_ms = (time.perf_counter() - inicio) * 1000
            resp.raise_for_status()
            alert_id = payload["alert_id"]
            model_called = _evento_model_called(db_path, alert_id)
            amostras.append(
                AmostraLatencia(
                    alert_id=alert_id,
                    total_ms=total_ms,
                    investigation_llm_ms=model_called[0] if model_called else None,
                    model_id=model_called[1] if model_called else None,
                    state_final=resp.json()["state"],
                )
            )
        valido = AuditChain(db_path=db_path).verify_chain()
    return amostras, valido
