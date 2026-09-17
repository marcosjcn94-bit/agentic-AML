"""Testes do pré-passo de indicadores (T1.5, DT-16, AGENTS.md §4.3): F01-F13 e F14+ com resultado conhecido."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from aml_guardian.config.triage import load_triage_rules
from aml_guardian.contracts.ingestion import (
    OccurrenceWindow,
    PaymentType,
    SanitizedAlert,
    SanitizedCustomer,
    SanitizedTransaction,
)
from aml_guardian.features import calcular_indicadores
from aml_guardian.triage.engine import MCPIndisponivelError

RULES = load_triage_rules()
BASE = datetime(2026, 9, 1, tzinfo=UTC)
TITULAR = "CONTA_01"


def _tx(
    idx: int,
    *,
    dias: float,
    valor: str,
    tipo: PaymentType,
    remetente: str,
    destinatario: str,
    destino: str = "BR",
) -> SanitizedTransaction:
    return SanitizedTransaction(
        transaction_id=f"tx-{idx:04d}",
        timestamp=BASE + timedelta(days=dias),
        amount_brl=valor,
        payment_type=tipo,
        sender_account=remetente,
        receiver_account=destinatario,
        sender_location="BR",
        receiver_location=destino,
        currency_sent="BRL",
        currency_received="BRL",
    )


# Cenário sintético único, reutilizado por todas as asserções de valor conhecido:
# entrada de CONTA_02, saídas para CONTA_03 (2x) e CONTA_04 (transfronteiriça), depósito em espécie
# seguido por envio transfronteiriço 1 dia depois (dispara F10 e alimenta F08 via detector de camadas).
_TRANSACOES = [
    _tx(1, dias=0, valor="3000.00", tipo=PaymentType.PIX, remetente="CONTA_02", destinatario=TITULAR),
    _tx(2, dias=1, valor="4000.00", tipo=PaymentType.TED, remetente=TITULAR, destinatario="CONTA_03"),
    _tx(3, dias=2, valor="2000.00", tipo=PaymentType.ESPECIE_DEPOSITO, remetente=TITULAR, destinatario=TITULAR),
    _tx(
        4,
        dias=3,
        valor="2000.00",
        tipo=PaymentType.TRANSFERENCIA_INTERNACIONAL,
        remetente=TITULAR,
        destinatario="CONTA_04",
        destino="US",
    ),
    _tx(5, dias=4, valor="500.00", tipo=PaymentType.PIX, remetente=TITULAR, destinatario="CONTA_03"),
]


def _alert() -> SanitizedAlert:
    return SanitizedAlert(
        alert_id=uuid4(),
        source_rule_id="LEG-TEST-01",
        selected_at=BASE,
        occurrence_window=OccurrenceWindow(start=BASE, end=BASE + timedelta(days=7)),
        sender_account=TITULAR,
        sender_customer=SanitizedCustomer(name="NOME_01", cpf_cnpj="CPF_01"),
        transactions=_TRANSACOES,
        pii_token_count=2,
        sanitizer_version="sanitizer-1",
    )


def _historico_180d(customer_id: str, window_days: int) -> dict:
    assert window_days == 180
    return {"status": "success", "customer_id": customer_id, "total_amount": "18000.00", "transaction_count": 40}


def _mcp02(customer_id: str, cpf_cnpj_token: str | None = None) -> dict:
    return {
        "status": "success",
        "customer_id": customer_id,
        "pep": "nao",
        "ceis": "nao",
        "cnep": "sim",
        "list_version": "v1",
    }


@pytest.fixture
def indicadores():
    return calcular_indicadores(_alert(), rules=RULES, history_fetcher=_historico_180d, restriction_checker=_mcp02)


def _por_id(indicadores, feature_id: str):
    achado = [f for f in indicadores.features if f.feature_id == feature_id]
    assert len(achado) == 1, f"{feature_id} ausente ou duplicado"
    return achado[0]


class TestValoresConhecidos:
    def test_features_version(self, indicadores):
        assert indicadores.features_version == 1

    def test_f01_tx_janela(self, indicadores):
        f = _por_id(indicadores, "F01")
        assert f.name == "tx_janela"
        assert f.value == 5
        assert len(f.transaction_ids) == 5

    def test_f02_total_brl(self, indicadores):
        f = _por_id(indicadores, "F02")
        assert f.value == 11500

    def test_f03_abaixo_limiar(self, indicadores):
        f = _por_id(indicadores, "F03")
        assert f.value == 5  # todas as 5 transações estão abaixo de 10.000,00

    def test_f04_dep_especie(self, indicadores):
        f = _por_id(indicadores, "F04")
        assert f.value == 1
        assert f.transaction_ids == ["tx-0003"]

    def test_f05_saida_pix_ted(self, indicadores):
        f = _por_id(indicadores, "F05")
        assert f.value == 2
        assert set(f.transaction_ids) == {"tx-0002", "tx-0005"}

    def test_f06_contrap_entrada(self, indicadores):
        f = _por_id(indicadores, "F06")
        assert f.value == 1
        assert f.transaction_ids == ["tx-0001"]

    def test_f07_contrap_saida(self, indicadores):
        f = _por_id(indicadores, "F07")
        assert f.value == 2  # CONTA_03 e CONTA_04

    def test_f08_camadas(self, indicadores):
        f = _por_id(indicadores, "F08")
        assert f.value == 2  # entrada e saída não vazias na janela de 30 dias

    def test_f09_transfronteira(self, indicadores):
        f = _por_id(indicadores, "F09")
        assert f.value == 1
        assert f.transaction_ids == ["tx-0004"]

    def test_f10_especie_depois_exterior(self, indicadores):
        f = _por_id(indicadores, "F10")
        assert f.value == "sim"
        assert f.transaction_ids == ["tx-0003", "tx-0004"]

    def test_f11_formato_uma_casa_decimal_com_x(self, indicadores):
        f = _por_id(indicadores, "F11")
        assert f.value == "16.4x"  # 11500 / ((18000/180) * 7)

    def test_f12_dias_ativos(self, indicadores):
        f = _por_id(indicadores, "F12")
        assert f.value == 5

    def test_f13_formato_listas(self, indicadores):
        f = _por_id(indicadores, "F13")
        assert f.value == "pep:nao,ceis:nao,cnep:sim"

    def test_f14_mais_ordenadas_por_brl_decrescente_e_so_tokens(self, indicadores):
        extras = sorted((f for f in indicadores.features if int(f.feature_id[1:]) >= 14), key=lambda f: f.feature_id)
        assert [f.name for f in extras] == ["CONTA_03", "CONTA_02", "CONTA_04"]
        assert [f.value for f in extras] == ["in=0 out=2 brl=4500", "in=1 out=0 brl=3000", "in=0 out=1 brl=2000"]
        for f in extras:
            assert f.name.startswith("CONTA_")  # só token, nenhum dado livre


class TestValoresInteirosExcetoF11:
    def test_f01_a_f09_e_f12_sao_inteiros(self, indicadores):
        for feature_id in ("F01", "F02", "F03", "F04", "F05", "F06", "F07", "F08", "F09", "F12"):
            assert isinstance(_por_id(indicadores, feature_id).value, int)

    def test_f11_nao_e_inteiro(self, indicadores):
        assert isinstance(_por_id(indicadores, "F11").value, str)
        assert _por_id(indicadores, "F11").value.endswith("x")


class TestFalhaMCP:
    def test_mcp01_indisponivel_propaga_erro(self):
        def fetcher_fora(customer_id: str, window_days: int) -> dict:
            raise ConnectionError("MCP-01 offline (teste)")

        with pytest.raises(MCPIndisponivelError):
            calcular_indicadores(_alert(), rules=RULES, history_fetcher=fetcher_fora, restriction_checker=_mcp02)

    def test_mcp02_indisponivel_propaga_erro(self):
        def checker_fora(customer_id: str, cpf_cnpj_token: str | None = None) -> dict:
            raise ConnectionError("MCP-02 offline (teste)")

        with pytest.raises(MCPIndisponivelError):
            calcular_indicadores(
                _alert(), rules=RULES, history_fetcher=_historico_180d, restriction_checker=checker_fora
            )
