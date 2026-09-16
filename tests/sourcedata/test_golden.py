from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from aml_guardian.contracts.ingestion import Alert, OccurrenceWindow, PaymentType, SenderCustomer, Transaction
from aml_guardian.sourcedata.golden import GoldenSetError, _distribui_agua, estrato_de_alerta
from aml_guardian.sourcedata.mapping import load_saml_d_mapping


def test_distribui_agua_divide_igualmente_quando_ha_sobra_para_todos():
    resultado = _distribui_agua({"A": 50, "B": 50, "C": 50}, total=30)
    assert resultado == {"A": 10, "B": 10, "C": 10}


def test_distribui_agua_trava_rotulo_escasso_e_redistribui_o_resto():
    resultado = _distribui_agua({"A": 2, "B": 50, "C": 50}, total=30)
    assert resultado == {"A": 2, "B": 14, "C": 14}


def test_distribui_agua_sobra_indivisivel_vai_para_os_primeiros_em_ordem_alfabetica():
    resultado = _distribui_agua({"A": 50, "B": 50, "C": 50}, total=31)
    assert resultado == {"A": 11, "B": 10, "C": 10}


def test_distribui_agua_encadeia_travas_em_mais_de_uma_rodada():
    resultado = _distribui_agua({"A": 1, "B": 2, "C": 50, "D": 50}, total=30)
    assert resultado == {"A": 1, "B": 2, "C": 14, "D": 13}


def test_distribui_agua_levanta_erro_se_total_pedido_excede_disponibilidade():
    with pytest.raises(GoldenSetError, match="disponib"):
        _distribui_agua({"A": 1, "B": 1}, total=10)


def _tx(indice: int) -> Transaction:
    return Transaction(
        transaction_id=f"tx-{indice:04d}",
        timestamp=datetime(2023, 1, indice, tzinfo=UTC),
        amount_brl="100.00",
        payment_type=PaymentType.PIX,
        sender_account="conta-1",
        receiver_account="conta-2",
        sender_location="BR",
        receiver_location="BR",
        currency_sent="BRL",
        currency_received="BRL",
    )


def _alerta(transacoes: list[Transaction]) -> Alert:
    return Alert(
        alert_id=uuid.uuid4(),
        source_rule_id="teste",
        selected_at=transacoes[-1].timestamp,
        occurrence_window=OccurrenceWindow(start=transacoes[0].timestamp, end=transacoes[-1].timestamp),
        sender_account="conta-1",
        sender_customer=SenderCustomer(name="Cliente Teste", cpf_cnpj="CPF_01"),
        transactions=transacoes,
    )


@pytest.fixture(scope="module")
def mapping():
    return load_saml_d_mapping()


def test_estrato_alerta_puro_critica_ignora_transacoes_normais(mapping):
    alerta = _alerta([_tx(1), _tx(2), _tx(3)])
    rotulos = {"tx-0001": "Normal_Fan_Out", "tx-0002": "Structuring", "tx-0003": "Normal_Fan_Out"}
    assert estrato_de_alerta(alerta, rotulos, mapping) == "Structuring"


def test_estrato_alerta_todo_normal_usa_rotulo_dominante(mapping):
    alerta = _alerta([_tx(1), _tx(2), _tx(3)])
    rotulos = {"tx-0001": "Normal_Fan_Out", "tx-0002": "Normal_Fan_Out", "tx-0003": "Normal_Cash_Deposits"}
    assert estrato_de_alerta(alerta, rotulos, mapping) == "Normal_Fan_Out"


def test_estrato_alerta_empate_normal_desempata_por_ordem_alfabetica(mapping):
    alerta = _alerta([_tx(1), _tx(2)])
    rotulos = {"tx-0001": "Normal_Fan_Out", "tx-0002": "Normal_Cash_Deposits"}
    assert estrato_de_alerta(alerta, rotulos, mapping) == "Normal_Cash_Deposits"


def test_estrato_alerta_mista_duas_tipologias_suspeitas_devolve_none(mapping):
    alerta = _alerta([_tx(1), _tx(2)])
    rotulos = {"tx-0001": "Structuring", "tx-0002": "Smurfing"}
    assert estrato_de_alerta(alerta, rotulos, mapping) is None
