"""Testes da Investigação v1 (T1.6, RF-05, DT-07, DT-16): paridade, teto de tokens, retries e RF-05."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from aml_guardian.config.litellm import load_litellm
from aml_guardian.config.triage import load_triage_rules
from aml_guardian.contracts.ingestion import (
    AlertState,
    OccurrenceWindow,
    PaymentType,
    SanitizedAlert,
    SanitizedCustomer,
    SanitizedTransaction,
    TriageLevel,
)
from aml_guardian.contracts.pipeline import Feature, TriageDecision
from aml_guardian.investigation import ContadorChamadas, run_investigation
from aml_guardian.investigation.contract import INVESTIGATION_INSTRUCTIONS, schema_geracao
from aml_guardian.investigation.litellm_client import resolver_params
from aml_guardian.investigation.prompt_builder import montar_prompt
from aml_guardian.triage import run_triage
from aml_guardian.triage.engine import TriageResult

RULES = load_triage_rules()
BASE = datetime(2026, 9, 1, tzinfo=UTC)
TITULAR = "CONTA_01"
MODEL = resolver_params(load_litellm()).model


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


def _historico_180d(customer_id: str, window_days: int) -> dict:
    return {"status": "success", "customer_id": customer_id, "total_amount": "5000.00", "transaction_count": 5}


def _mcp02_limpo(customer_id: str, cpf_cnpj_token: str | None = None) -> dict:
    return {
        "status": "success",
        "customer_id": customer_id,
        "pep": "nao",
        "ceis": "nao",
        "cnep": "nao",
        "list_version": "v1",
    }


def _triagem_investigar() -> TriageResult:
    resultado = run_triage(_alerta_fragmentacao(), rules=RULES, restriction_checker=_mcp02_limpo)
    assert resultado.decision.level is TriageLevel.INVESTIGAR
    return resultado


def _mock(t: str, c: float, r: str, e: list[int]) -> str:
    return json.dumps({"t": t, "c": c, "r": r, "e": e})


# --- Paridade com scripts/bench_ollama.py (não alterado) ---


def _carregar_bench_ollama():
    caminho = Path(__file__).resolve().parents[2] / "scripts" / "bench_ollama.py"
    spec = importlib.util.spec_from_file_location("bench_ollama_ref", caminho)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo  # dataclasses precisa achar o módulo em sys.modules ao decorar
    spec.loader.exec_module(modulo)
    return modulo


class TestParidadeComBenchmark:
    def test_instrucoes_identicas(self):
        bench = _carregar_bench_ollama()
        assert INVESTIGATION_INSTRUCTIONS == bench.INVESTIGATION_INSTRUCTIONS

    def test_schema_identico(self):
        bench = _carregar_bench_ollama()
        feature_ids = ["F01", "F02", "F03", "F14"]
        assert schema_geracao(feature_ids) == bench.investigation_schema(feature_ids)


# --- Teto de 300 tokens (montador) ---


class TestTetoDeTokens:
    def test_remove_f14_menor_brl_primeiro_com_empate_por_maior_feature_id(self, monkeypatch):
        alerta = _alerta_fragmentacao()
        base = [Feature(feature_id=f"F{i:02d}", name="indicador", value=1, transaction_ids=[]) for i in range(1, 14)]
        extras = [
            Feature(feature_id="F14", name="CONTA_A", value="in=1 out=0 brl=100", transaction_ids=[]),
            Feature(feature_id="F15", name="CONTA_B", value="in=1 out=0 brl=100", transaction_ids=[]),
            Feature(feature_id="F16", name="CONTA_C", value="in=1 out=0 brl=900", transaction_ids=[]),
        ]

        sem_extras = montar_prompt(MODEL, alerta, [], base)
        com_extras = montar_prompt(MODEL, alerta, [], base + extras)
        assert com_extras.tokens > sem_extras.tokens

        teto = (sem_extras.tokens + com_extras.tokens) // 2
        monkeypatch.setattr("aml_guardian.investigation.prompt_builder.MAX_PROMPT_TOKENS", teto)

        resultado = montar_prompt(MODEL, alerta, [], base + extras)
        assert resultado.dentro_do_teto
        assert resultado.descartadas
        # F14 e F15 empatam em brl=100: o de maior feature_id (F15) sai primeiro.
        assert resultado.descartadas[0] == "F15"

    def test_ainda_acima_do_teto_needs_human_sem_chamada(self, monkeypatch):
        monkeypatch.setattr("aml_guardian.investigation.prompt_builder.MAX_PROMPT_TOKENS", 1)
        triagem = _triagem_investigar()
        contador = ContadorChamadas()

        resultado = run_investigation(
            _alerta_fragmentacao_com_mesmo_id(triagem),
            triagem.decision,
            triage_rules=RULES,
            history_fetcher=_historico_180d,
            restriction_checker=_mcp02_limpo,
            contador=contador,
        )

        assert resultado.state is AlertState.NEEDS_HUMAN
        assert contador.chamadas == 0


def _alerta_fragmentacao_com_mesmo_id(triagem: TriageResult) -> SanitizedAlert:
    """Reconstroi um alerta com o mesmo cenário de fragmentação e o `alert_id` da triagem já feita."""
    cfg = RULES.detectores_criticos.fragmentacao
    transacoes = [
        _tx(i, dias=i, valor="500.00", remetente=TITULAR, destinatario="CONTA_02") for i in range(cfg.min_transacoes)
    ]
    return SanitizedAlert(
        alert_id=triagem.decision.alert_id,
        source_rule_id="LEG-TEST-01",
        selected_at=BASE,
        occurrence_window=OccurrenceWindow(start=BASE, end=BASE + timedelta(days=7)),
        sender_account=TITULAR,
        sender_customer=SanitizedCustomer(name="NOME_01", cpf_cnpj="CPF_01"),
        transactions=transacoes,
        pii_token_count=2,
        sanitizer_version="sanitizer-1",
    )


# --- Fluxo completo com modelo simulado (`mock_response` do LiteLLM) ---


class TestFluxoComModeloSimulado:
    def test_saida_valida_investigating(self):
        triagem = _triagem_investigar()
        contador = ContadorChamadas()

        resultado = run_investigation(
            _alerta_fragmentacao_com_mesmo_id(triagem),
            triagem.decision,
            triage_rules=RULES,
            history_fetcher=_historico_180d,
            restriction_checker=_mcp02_limpo,
            contador=contador,
            mock_response=_mock("Structuring", 0.7, "COMUNICAR", [3]),
        )

        assert resultado.state is AlertState.INVESTIGATING
        assert resultado.investigation.evidence_feature_ids == ["F03"]
        assert resultado.discarded_evidence_ids == []
        assert contador.chamadas == 1

    def test_json_invalido_apos_retries_needs_human(self):
        triagem = _triagem_investigar()
        contador = ContadorChamadas()

        resultado = run_investigation(
            _alerta_fragmentacao_com_mesmo_id(triagem),
            triagem.decision,
            triage_rules=RULES,
            history_fetcher=_historico_180d,
            restriction_checker=_mcp02_limpo,
            contador=contador,
            mock_response="isto nao e json",
        )

        assert resultado.state is AlertState.NEEDS_HUMAN
        assert contador.chamadas == 3  # 1 tentativa inicial + 2 retries (AGENTS.md §1)

    def test_evidencia_inexistente_descartada_e_registrada(self):
        triagem = _triagem_investigar()
        contador = ContadorChamadas()

        resultado = run_investigation(
            _alerta_fragmentacao_com_mesmo_id(triagem),
            triagem.decision,
            triage_rules=RULES,
            history_fetcher=_historico_180d,
            restriction_checker=_mcp02_limpo,
            contador=contador,
            mock_response=_mock("Structuring", 0.6, "COMUNICAR", [99]),
        )

        assert resultado.state is AlertState.INVESTIGATING
        assert resultado.investigation.evidence_feature_ids == []
        assert resultado.discarded_evidence_ids == ["F99"]

    def test_detector_critico_com_arquivar_needs_human(self):
        triagem = _triagem_investigar()
        assert any(regra.critical for regra in triagem.decision.fired_rules)

        resultado = run_investigation(
            _alerta_fragmentacao_com_mesmo_id(triagem),
            triagem.decision,
            triage_rules=RULES,
            history_fetcher=_historico_180d,
            restriction_checker=_mcp02_limpo,
            mock_response=_mock("NENHUMA", 0.1, "ARQUIVAR", []),
        )

        assert resultado.state is AlertState.NEEDS_HUMAN
        assert resultado.investigation is not None  # preserva o que já foi produzido (AGENTS.md §2.8)

    def test_tipologia_critica_com_arquivar_needs_human_mesmo_sem_detector(self):
        alerta = _alerta_fragmentacao()
        triagem_sem_detector = TriageDecision(
            alert_id=alerta.alert_id, level=TriageLevel.INVESTIGAR, fired_rules=[], rules_version=RULES.rules_version
        )

        resultado = run_investigation(
            alerta,
            triagem_sem_detector,
            triage_rules=RULES,
            history_fetcher=_historico_180d,
            restriction_checker=_mcp02_limpo,
            mock_response=_mock("Deposit-Send", 0.4, "ARQUIVAR", []),
        )

        assert resultado.state is AlertState.NEEDS_HUMAN

    def test_arquivar_sem_criticidade_nenhuma_nao_vai_a_needs_human(self):
        alerta = _alerta_fragmentacao()
        triagem_sem_detector = TriageDecision(
            alert_id=alerta.alert_id, level=TriageLevel.INVESTIGAR, fired_rules=[], rules_version=RULES.rules_version
        )

        resultado = run_investigation(
            alerta,
            triagem_sem_detector,
            triage_rules=RULES,
            history_fetcher=_historico_180d,
            restriction_checker=_mcp02_limpo,
            mock_response=_mock("Cash Withdrawal", 0.2, "ARQUIVAR", []),
        )

        assert resultado.state is AlertState.INVESTIGATING


# --- Teste real com Ollama local (qwen2.5:1.5b) ---


@pytest.mark.ollama
def test_investigacao_real_com_ollama_local():
    triagem = _triagem_investigar()

    resultado = run_investigation(
        _alerta_fragmentacao_com_mesmo_id(triagem),
        triagem.decision,
        triage_rules=RULES,
        history_fetcher=_historico_180d,
        restriction_checker=_mcp02_limpo,
    )

    assert resultado.state in (AlertState.INVESTIGATING, AlertState.NEEDS_HUMAN)
    if resultado.state is AlertState.INVESTIGATING:
        assert resultado.investigation is not None
