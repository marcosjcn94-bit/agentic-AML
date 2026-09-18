"""Roda o golden set completo `data/golden/v1` pelo pipeline real via API-01 (fecha os gates "não medida" do
`SPEC.md` §10 registrados em `MEMORY.md` "M7 · gap conhecido").

Reaproveita os fakes de MCP-03/04 de `eval/fixtures.py` (T1.13): `select_citations` só chama o searcher quando a
tipologia tem `applicability` curado no mapeamento (`data/mappings/saml_d_to_cc4001.yaml`, `mapping_version` 2 —
hoje só `Structuring`); para as demais o resultado é sempre "sem citação" por desenho, não pelo fake. MCP-01/02
usam os defaults de `GraphDeps` (`mcp_servers/server.py`), que já são mocks determinísticos em produção nesta PoC.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient

from aml_guardian.api.app import create_app
from aml_guardian.api.health import HealthDeps
from aml_guardian.api.state import AppState
from aml_guardian.audit.chain import AuditChain
from aml_guardian.contracts.runtime import InvestigationState
from aml_guardian.eval.fixtures import (
    mcp01_historico_vazio,
    mcp02_sem_ocorrencia,
    norms_getter_fixo,
    norms_searcher_fixo,
)
from aml_guardian.graph.build import build_graph
from aml_guardian.graph.checkpoint import sqlite_checkpointer
from aml_guardian.graph.deps import GraphDeps
from aml_guardian.persistence.db import get_connection, init_db
from aml_guardian.sourcedata.golden_manifest import GoldenManifest, carrega_manifesto
from aml_guardian.sourcedata.mapping import SamlDMapping, load_saml_d_mapping

_TOKEN_SISTEMA = "eval-golden-token-sistema"


@dataclass(frozen=True)
class AmostraGolden:
    alert_id: str
    estrato: str
    critica: bool
    normal: bool
    total_ms: float
    state_final: str
    dossier_type: str | None
    citations_propostas: int
    citations_verificadas: int
    tokens_in: int
    tokens_out: int
    prazo_ok: bool | None


@contextmanager
def _com_token_sistema() -> Iterator[None]:
    anterior = os.environ.get("API_TOKEN_SISTEMA")
    os.environ["API_TOKEN_SISTEMA"] = _TOKEN_SISTEMA
    try:
        yield
    finally:
        if anterior is None:
            os.environ.pop("API_TOKEN_SISTEMA", None)
        else:
            os.environ["API_TOKEN_SISTEMA"] = anterior


def _monta_cliente(tmp_dir: Path, mock_response: str | None) -> tuple[TestClient, AppState]:
    db_path = tmp_dir / "golden.sqlite"
    init_db(db_path)
    model_overrides: dict[str, object] = {}
    if mock_response is not None:
        model_overrides["mock_response"] = mock_response
    state = AppState(
        graph_deps=GraphDeps(
            corpus_version="golden-v1",
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
            corpus_version_getter=lambda: "golden-v1",
        ),
        db_path=db_path,
        checkpoint_path=tmp_dir / "golden-checkpoints.sqlite",
    )
    return TestClient(create_app(state=state)), state


def _tokens_do_alerta(db_path: Path, alert_id: str) -> tuple[int, int]:
    tokens_in = tokens_out = 0
    for evento in AuditChain(db_path=db_path).get_events(alert_id=alert_id):
        if evento.event_type == "MODEL_CALLED":
            tokens_in += evento.tokens_in
            tokens_out += evento.tokens_out
    return tokens_in, tokens_out


def _estado_completo(state: AppState, alert_id: str) -> InvestigationState | None:
    with sqlite_checkpointer(state.checkpoint_path) as checkpointer:
        compiled = build_graph(state.graph_deps).compile(checkpointer=checkpointer)
        snapshot = compiled.get_state({"configurable": {"thread_id": alert_id}})
    if not snapshot.values:
        return None
    return InvestigationState.model_validate(snapshot.values)


def _classifica_estrato(estrato: str, mapping: SamlDMapping) -> tuple[bool, bool]:
    """Devolve (critica, normal) do rótulo bruto do SAML-D gravado no manifesto."""
    if estrato in mapping.normais:
        return False, True
    return mapping.tipologias[estrato].critica, False


def roda_golden(
    manifest_path: Path,
    payloads_dir: Path,
    tmp_dir: Path,
    *,
    mock_response: str | None,
    limit: int | None = None,
) -> tuple[GoldenManifest, list[AmostraGolden], bool, Path]:
    """Roda o golden set (ou os `limit` primeiros alertas do manifesto, para validação rápida) via `POST /alerts`.

    Devolve (manifesto, amostras, auditoria_valida, db_path) — `db_path` fica disponível para o chamador rodar a
    varredura de privacidade (RNF-05) sobre o mesmo banco desta execução, sem reabrir a amostra.
    """
    manifesto = carrega_manifesto(manifest_path)
    mapping = load_saml_d_mapping()
    itens = manifesto.alertas if limit is None else manifesto.alertas[:limit]

    with _com_token_sistema():
        client, state = _monta_cliente(tmp_dir, mock_response)
        amostras: list[AmostraGolden] = []
        for item in itens:
            alert_id = str(item.alert_id)
            payload = json.loads((payloads_dir / f"{alert_id}.json").read_text(encoding="utf-8"))

            inicio = time.perf_counter()
            resp = client.post("/alerts", json=payload, headers={"Authorization": f"Bearer {_TOKEN_SISTEMA}"})
            total_ms = (time.perf_counter() - inicio) * 1000
            resp.raise_for_status()
            state_final = resp.json()["state"]

            investigation_state = _estado_completo(state, alert_id)
            dossier = investigation_state.dossier if investigation_state else None
            review = investigation_state.review if investigation_state else None
            citations_propostas = len(investigation_state.citations) if investigation_state else 0
            tokens_in, tokens_out = _tokens_do_alerta(state.db_path, alert_id)

            prazo_ok = None
            if dossier is not None:
                d = dossier.deadlines
                prazo_ok = d.selecao_em <= d.prazo_interno <= d.prazo_regulatorio_analise

            critica, normal = _classifica_estrato(item.estrato, mapping)
            amostras.append(
                AmostraGolden(
                    alert_id=alert_id,
                    estrato=item.estrato,
                    critica=critica,
                    normal=normal,
                    total_ms=total_ms,
                    state_final=state_final,
                    dossier_type=dossier.type.value if dossier else None,
                    citations_propostas=citations_propostas,
                    citations_verificadas=len(review.verified_citations) if review else 0,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    prazo_ok=prazo_ok,
                )
            )
        valido = AuditChain(db_path=state.db_path).verify_chain()
    return manifesto, amostras, valido, state.db_path


def escaneia_privacidade(db_path: Path, payloads_dir: Path, alert_ids: list[str]) -> tuple[bool, int]:
    """Varre `audit_events`/`alert_records` (DT-12/DT-05) por CPF/CNPJ em claro dos payloads golden rodados —
    mesma técnica de `tests/privacy/test_canary.py` (T1.12), aplicada aos valores sintéticos reais da amostra."""
    marcadores = set()
    for alert_id in alert_ids:
        payload = json.loads((payloads_dir / f"{alert_id}.json").read_text(encoding="utf-8"))
        marcadores.add(payload["sender_customer"]["cpf_cnpj"])

    with closing(get_connection(db_path)) as conn:
        cursor = conn.cursor()
        pedacos: list[str] = []
        for tabela in ("audit_events", "alert_records"):  # nomes fixos de `persistence/db.py`, não input externo
            cursor.execute(f"SELECT * FROM {tabela}")  # noqa: S608 - nome de tabela é literal fixo, não input
            for linha in cursor.fetchall():
                pedacos.append(" ".join(str(valor) for valor in linha if valor is not None))
        conteudo = " ".join(pedacos)

    ocorrencias = sum(1 for marcador in marcadores if marcador in conteudo)
    return ocorrencias == 0, ocorrencias
