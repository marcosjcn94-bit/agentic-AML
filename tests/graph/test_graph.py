"""Testes do grafo LangGraph (T1.10, RF-10, RF-11, DT-14): roteamento, envelope, NEEDS_HUMAN e checkpoint."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from aml_guardian.config.triage import load_triage_rules
from aml_guardian.contracts.envelope import A2AEnvelope, InvestigationTask, Node
from aml_guardian.contracts.ingestion import (
    AlertState,
    OccurrenceWindow,
    PaymentType,
    SanitizedAlert,
    SanitizedCustomer,
    SanitizedTransaction,
    TriageLevel,
)
from aml_guardian.contracts.pipeline import DossierType, TriageDecision
from aml_guardian.contracts.runtime import Budget, InvestigationState
from aml_guardian.graph.build import run_alert
from aml_guardian.graph.checkpoint import sqlite_checkpointer
from aml_guardian.graph.deps import GraphDeps
from aml_guardian.norms.normalize import text_sha256

RULES = load_triage_rules()
BASE = datetime(2026, 9, 1, tzinfo=UTC)
TITULAR = "CONTA_01"
TEXTO_NORMATIVO = "Fragmentação de depósitos em espécie para dissimular o valor total da movimentação."


def _tx(idx: int, *, dias: float, valor: str, remetente: str, destinatario: str) -> SanitizedTransaction:
    return SanitizedTransaction(
        transaction_id=f"tx-{idx:04d}",
        timestamp=BASE + timedelta(days=dias),
        amount_brl=valor,
        payment_type=PaymentType.PIX,
        sender_account=remetente,
        receiver_account=destinatario,
        sender_location="BR",
        receiver_location="BR",
        currency_sent="BRL",
        currency_received="BRL",
    )


def _alerta_fragmentacao() -> SanitizedAlert:
    """Dispara o detector crítico de fragmentação (`TriageLevel.INVESTIGAR`)."""
    cfg = RULES.detectores_criticos.fragmentacao
    transacoes = [
        _tx(i, dias=i, valor="500.00", remetente=TITULAR, destinatario="CONTA_02") for i in range(cfg.min_transacoes)
    ]
    return SanitizedAlert(
        alert_id=uuid4(),
        source_rule_id="LEG-TEST-01",
        selected_at=BASE,
        occurrence_window=OccurrenceWindow(start=BASE, end=BASE + timedelta(days=7)),
        sender_account=TITULAR,
        sender_customer=SanitizedCustomer(name="NOME_01", cpf_cnpj="CPF_01"),
        transactions=transacoes,
        pii_token_count=2,
        sanitizer_version="sanitizer-1",
    )


def _alerta_sem_detector() -> SanitizedAlert:
    """Sem nenhum detector crítico disparado (`TriageLevel.PROPOR_ARQUIVAMENTO`)."""
    return SanitizedAlert(
        alert_id=uuid4(),
        source_rule_id="LEG-TEST-02",
        selected_at=BASE,
        occurrence_window=OccurrenceWindow(start=BASE, end=BASE + timedelta(days=1)),
        sender_account=TITULAR,
        sender_customer=SanitizedCustomer(name="NOME_01", cpf_cnpj="CPF_01"),
        transactions=[_tx(1, dias=0, valor="150.00", remetente=TITULAR, destinatario="CONTA_02")],
        pii_token_count=2,
        sanitizer_version="sanitizer-1",
    )


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


def _fake_searcher(*, ok: bool = True):
    def searcher(query: str, top_k: int, corpus_version: str) -> dict:
        if not ok:
            return {"error": "INTERNAL_ERROR", "message": "MCP-03 fora do ar", "retryable": True}
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


def _initial_state(alert: SanitizedAlert) -> InvestigationState:
    return InvestigationState(
        alert_id=alert.alert_id,
        trace_id=uuid4(),
        state=AlertState.SANITIZED,
        sanitized_alert=alert,
        budget=Budget(tokens_used=0, started_at=BASE),
    )


class TestCaminhoInvestigar:
    def test_investigar_percorre_ate_dossier_com_citacao_verificada(self):
        alerta = _alerta_fragmentacao()
        deps = GraphDeps(
            corpus_version="corpus-v1",
            triage_rules=RULES,
            history_fetcher=_historico_180d,
            restriction_checker=_mcp02_limpo,
            searcher=_fake_searcher(),
            passage_getter=_fake_getter(),
            model_overrides={"mock_response": _mock_investigation("Structuring", 0.82, "COMUNICAR", [3])},
        )

        with sqlite_checkpointer(":memory:") as checkpointer:
            estado_final, _compiled, _config = run_alert(_initial_state(alerta), deps, checkpointer)

        assert estado_final.state is AlertState.DRAFT_READY
        assert estado_final.triage.level is TriageLevel.INVESTIGAR
        assert estado_final.investigation is not None
        assert estado_final.review is not None
        assert len(estado_final.review.verified_citations) >= 1
        assert estado_final.dossier.type is DossierType.COS
        assert len(estado_final.dossier.citations) >= 1


class TestCaminhoProporArquivamento:
    def test_propor_arquivamento_vai_direto_ao_dossier(self):
        alerta = _alerta_sem_detector()
        deps = GraphDeps(
            corpus_version="corpus-v1",
            triage_rules=RULES,
            history_fetcher=_historico_180d,
            restriction_checker=_mcp02_limpo,
        )

        with sqlite_checkpointer(":memory:") as checkpointer:
            estado_final, _compiled, _config = run_alert(_initial_state(alerta), deps, checkpointer)

        assert estado_final.state is AlertState.DRAFT_READY
        assert estado_final.triage.level is TriageLevel.PROPOR_ARQUIVAMENTO
        assert estado_final.investigation is None  # nunca passou pela Investigação (AGENTS.md §5)
        assert estado_final.dossier.type is DossierType.ARQUIVAMENTO


class TestErroDeQualquerNoVaiParaNeedsHuman:
    def test_mcp03_indisponivel_na_retrieval_preserva_producao_parcial(self):
        alerta = _alerta_fragmentacao()
        deps = GraphDeps(
            corpus_version="corpus-v1",
            triage_rules=RULES,
            history_fetcher=_historico_180d,
            restriction_checker=_mcp02_limpo,
            searcher=_fake_searcher(ok=False),
            passage_getter=_fake_getter(),
            model_overrides={"mock_response": _mock_investigation("Structuring", 0.82, "COMUNICAR", [3])},
        )

        with sqlite_checkpointer(":memory:") as checkpointer:
            estado_final, _compiled, _config = run_alert(_initial_state(alerta), deps, checkpointer)

        assert estado_final.state is AlertState.NEEDS_HUMAN
        assert estado_final.failure_reason is not None
        # produção parcial preservada (AGENTS.md §2.8): triage, features e investigation já calculados sobrevivem
        assert estado_final.triage is not None
        assert estado_final.features is not None
        assert estado_final.investigation is not None
        assert estado_final.dossier is None


class TestEnvelopeComPayloadInvalido:
    def test_payload_de_outra_aresta_e_rejeitado(self):
        alerta = _alerta_fragmentacao()
        triagem = TriageDecision(
            alert_id=alerta.alert_id, level=TriageLevel.INVESTIGAR, fired_rules=[], rules_version=1
        )

        with pytest.raises(ValueError, match="exige type/schema_version"):
            A2AEnvelope(
                message_id=uuid4(),
                alert_id=alerta.alert_id,
                trace_id=uuid4(),
                from_node=Node.TRIAGE,
                to_node=Node.INVESTIGATION,
                type="TASK",
                schema_version="DT-06.v1",  # aresta triage→investigation exige DT-04+DT-06.v1 (InvestigationTask)
                payload=triagem,
                created_at=BASE,
            )

    def test_aresta_inexistente_e_rejeitada(self):
        alerta = _alerta_fragmentacao()
        triagem = TriageDecision(
            alert_id=alerta.alert_id, level=TriageLevel.INVESTIGAR, fired_rules=[], rules_version=1
        )

        with pytest.raises(ValueError, match="aresta"):
            A2AEnvelope(
                message_id=uuid4(),
                alert_id=alerta.alert_id,
                trace_id=uuid4(),
                from_node=Node.DOSSIER,
                to_node=Node.TRIAGE,
                type="TASK",
                schema_version="DT-06.v1",
                payload=triagem,
                created_at=BASE,
            )

    def test_payload_correto_e_aceito(self):
        alerta = _alerta_fragmentacao()
        triagem = TriageDecision(
            alert_id=alerta.alert_id, level=TriageLevel.INVESTIGAR, fired_rules=[], rules_version=1
        )

        envelope = A2AEnvelope(
            message_id=uuid4(),
            alert_id=alerta.alert_id,
            trace_id=uuid4(),
            from_node=Node.TRIAGE,
            to_node=Node.INVESTIGATION,
            type="TASK",
            schema_version="DT-04+DT-06.v1",
            payload=InvestigationTask(sanitized_alert=alerta, triage=triagem),
            created_at=BASE,
        )
        assert envelope.payload.triage == triagem


class TestCheckpointPorNo:
    def test_checkpoint_presente_apos_cada_no(self):
        alerta = _alerta_sem_detector()
        deps = GraphDeps(
            corpus_version="corpus-v1",
            triage_rules=RULES,
            history_fetcher=_historico_180d,
            restriction_checker=_mcp02_limpo,
        )

        with sqlite_checkpointer(":memory:") as checkpointer:
            estado_final, compiled, config = run_alert(_initial_state(alerta), deps, checkpointer)
            historico = list(compiled.get_state_history(config))

        assert estado_final.state is AlertState.DRAFT_READY
        # 2 nós percorridos (triage, dossier): checkpoint inicial + 1 por nó, no mínimo (langgraph-checkpoint-sqlite)
        assert len(historico) >= 3
