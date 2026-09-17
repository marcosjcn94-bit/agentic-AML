"""Testes da triagem inicial (T1.4, RF-03, DT-06): detectores críticos e decisão versionada."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

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
from aml_guardian.triage import run_triage

RULES = load_triage_rules()
TZ = UTC
BASE = datetime(2026, 9, 1, tzinfo=TZ)
TITULAR = "CONTA_01"


def _tx(
    idx: int,
    *,
    dias: float = 0,
    valor: str = "100.00",
    tipo: PaymentType = PaymentType.PIX,
    remetente: str = TITULAR,
    destinatario: str = "CONTA_02",
    origem: str = "BR",
    destino: str = "BR",
) -> SanitizedTransaction:
    return SanitizedTransaction(
        transaction_id=f"tx-{idx:04d}",
        timestamp=BASE + timedelta(days=dias),
        amount_brl=valor,
        payment_type=tipo,
        sender_account=remetente,
        receiver_account=destinatario,
        sender_location=origem,
        receiver_location=destino,
        currency_sent="BRL",
        currency_received="BRL",
    )


def _alert(transactions: list[SanitizedTransaction]) -> SanitizedAlert:
    return SanitizedAlert(
        alert_id=uuid4(),
        source_rule_id="LEG-TEST-01",
        selected_at=BASE,
        occurrence_window=OccurrenceWindow(start=BASE, end=BASE + timedelta(days=10)),
        sender_account=TITULAR,
        sender_customer=SanitizedCustomer(name="NOME_01", cpf_cnpj="CPF_01"),
        transactions=transactions,
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
        "list_version": "2026-09-17",
    }


def _mcp02_com_acerto(customer_id: str, cpf_cnpj_token: str | None = None) -> dict:
    result = _mcp02_limpo(customer_id, cpf_cnpj_token)
    return result | {"pep": "sim"}


def _mcp02_indisponivel(customer_id: str, cpf_cnpj_token: str | None = None) -> dict:
    raise ConnectionError("MCP-02 offline (teste)")


def _sem_nenhum_detector() -> SanitizedAlert:
    return _alert([_tx(1, valor="50.00")])


class TestDetectoresCriticos:
    """Cada detector crítico disparado leva a INVESTIGAR, nunca a PROPOR_ARQUIVAMENTO (RF-03)."""

    def test_fragmentacao_dispara_investigar(self):
        cfg = RULES.detectores_criticos.fragmentacao
        transacoes = [_tx(i, dias=i, valor="500.00") for i in range(cfg.min_transacoes)]
        resultado = run_triage(_alert(transacoes), rules=RULES, restriction_checker=_mcp02_limpo)

        assert resultado.state is AlertState.TRIAGED
        assert resultado.decision.level is TriageLevel.INVESTIGAR
        assert any(r.rule_id == "FRAGMENTACAO" and r.critical for r in resultado.decision.fired_rules)

    def test_camadas_dispara_investigar(self):
        cfg = RULES.detectores_criticos.camadas
        transacoes = [
            _tx(1, valor="15000.00", remetente="CONTA_02", destinatario=TITULAR),
            _tx(2, valor="16000.00", remetente="CONTA_03", destinatario=TITULAR),
            _tx(3, valor="17000.00", remetente=TITULAR, destinatario="CONTA_04"),
        ]
        resultado = run_triage(_alert(transacoes), rules=RULES, restriction_checker=_mcp02_limpo)

        assert resultado.state is AlertState.TRIAGED
        assert resultado.decision.level is TriageLevel.INVESTIGAR
        assert any(r.rule_id == "CAMADAS" and r.critical for r in resultado.decision.fired_rules)
        assert cfg.profundidade_minima == 2  # documenta a premissa do cenário sintético

    def test_especie_depois_exterior_dispara_investigar(self):
        transacoes = [
            _tx(1, dias=0, valor="9000.00", tipo=PaymentType.ESPECIE_DEPOSITO, remetente=TITULAR, destinatario=TITULAR),
            _tx(
                2,
                dias=1,
                valor="9000.00",
                tipo=PaymentType.TRANSFERENCIA_INTERNACIONAL,
                remetente=TITULAR,
                destinatario="CONTA_09",
                destino="US",
            ),
        ]
        resultado = run_triage(_alert(transacoes), rules=RULES, restriction_checker=_mcp02_limpo)

        assert resultado.state is AlertState.TRIAGED
        assert resultado.decision.level is TriageLevel.INVESTIGAR
        assert any(r.rule_id == "ESPECIE_DEPOIS_EXTERIOR" and r.critical for r in resultado.decision.fired_rules)

    def test_lista_restricao_dispara_investigar(self):
        resultado = run_triage(_sem_nenhum_detector(), rules=RULES, restriction_checker=_mcp02_com_acerto)

        assert resultado.state is AlertState.TRIAGED
        assert resultado.decision.level is TriageLevel.INVESTIGAR
        assert any(r.rule_id == "LISTA_RESTRICAO" and r.critical for r in resultado.decision.fired_rules)


class TestSemDetector:
    def test_alerta_sem_detector_propoe_arquivamento(self):
        resultado = run_triage(_sem_nenhum_detector(), rules=RULES, restriction_checker=_mcp02_limpo)

        assert resultado.state is AlertState.TRIAGED
        assert resultado.decision.level is TriageLevel.PROPOR_ARQUIVAMENTO
        assert resultado.decision.fired_rules == []


class TestDeterminismo:
    def test_mesma_entrada_mesma_rules_version_mesma_decisao(self):
        alerta = _sem_nenhum_detector()
        primeiro = run_triage(alerta, rules=RULES, restriction_checker=_mcp02_limpo)
        segundo = run_triage(alerta, rules=RULES, restriction_checker=_mcp02_limpo)

        assert primeiro.decision.model_dump() == segundo.decision.model_dump()
        assert primeiro.decision.rules_version == RULES.rules_version


class TestMCP02Indisponivel:
    def test_mcp02_fora_leva_a_needs_human(self):
        resultado = run_triage(_sem_nenhum_detector(), rules=RULES, restriction_checker=_mcp02_indisponivel)

        assert resultado.state is AlertState.NEEDS_HUMAN
        assert resultado.decision is None
        assert resultado.failure_reason is not None

    def test_mcp02_resposta_sem_status_sucesso_leva_a_needs_human(self):
        def checker(customer_id: str, cpf_cnpj_token: str | None = None) -> dict:
            return {"error": "TIMEOUT", "retryable": True}

        resultado = run_triage(_sem_nenhum_detector(), rules=RULES, restriction_checker=checker)

        assert resultado.state is AlertState.NEEDS_HUMAN
        assert resultado.failure_reason is not None
