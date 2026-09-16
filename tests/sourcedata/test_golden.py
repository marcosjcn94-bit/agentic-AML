from __future__ import annotations

import json
import uuid
import uuid as uuid_mod
from contextlib import closing
from datetime import UTC, datetime

import pytest

from aml_guardian.contracts.ingestion import (
    Alert,
    OccurrenceWindow,
    PaymentType,
    SenderCustomer,
    SyntheticCustomer,
    Transaction,
)
from aml_guardian.sourcedata.core_db import conecta, cria_schema, grava_clientes, grava_meta, grava_transacoes
from aml_guardian.sourcedata.golden import GoldenSetError, _distribui_agua, estrato_de_alerta, particiona_contas
from aml_guardian.sourcedata.golden_manifest import (
    carrega_manifesto,
    constroi_manifesto,
    grava_golden,
    payload_sha256,
)
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


def _monta_banco_particao(tmp_path, *, contas_suspeitas: int, contas_normais: int):
    db = tmp_path / "particao.sqlite"
    with closing(conecta(db)) as conn:
        cria_schema(conn)
        clientes = [
            SyntheticCustomer(
                customer_id=f"cli-{i}",
                name=f"Cliente {i}",
                cpf_cnpj=f"CPF_{i:04d}",
                accounts=[f"conta-{i}"],
                segment="PF",
                restriction_flags=[],
            )
            for i in range(contas_suspeitas + contas_normais)
        ]
        grava_clientes(conn, clientes)
        transacoes = []
        for i in range(contas_suspeitas):
            transacoes.append((_tx_conta(f"conta-{i}", 1), "Structuring", True))
        for i in range(contas_suspeitas, contas_suspeitas + contas_normais):
            transacoes.append((_tx_conta(f"conta-{i}", 1), "Normal_Fan_Out", False))
        grava_transacoes(conn, transacoes)
        grava_meta(conn, {"seed": 1})
        conn.commit()
    return db


def _tx_conta(conta: str, indice: int) -> Transaction:
    tx = _tx(indice)
    return tx.model_copy(update={"transaction_id": f"tx-{conta}-{indice:04d}", "sender_account": conta})


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


def test_particiona_contas_e_disjunta_e_cobre_todas_as_contas(tmp_path):
    db = _monta_banco_particao(tmp_path, contas_suspeitas=20, contas_normais=20)
    with closing(conecta(db)) as conn:
        particao = particiona_contas(conn, seed=20260916)
    assert particao.golden.isdisjoint(particao.desenvolvimento)
    assert particao.golden | particao.desenvolvimento == {f"conta-{i}" for i in range(40)}
    assert particao.golden  # não vazio com essas frações


def test_particiona_contas_e_deterministica_pela_seed(tmp_path):
    db = _monta_banco_particao(tmp_path, contas_suspeitas=20, contas_normais=20)
    with closing(conecta(db)) as conn:
        p1 = particiona_contas(conn, seed=7)
        p2 = particiona_contas(conn, seed=7)
    assert p1 == p2


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


def test_payload_sha256_estavel_para_o_mesmo_alerta():
    alerta = _alerta([_tx(1)])
    assert payload_sha256(alerta) == payload_sha256(alerta)
    assert len(payload_sha256(alerta)) == 64


def test_constroi_manifesto_hash_reproduz_para_a_mesma_selecao():
    selecionados = [(_alerta([_tx(1)]), "Structuring")]
    m1 = constroi_manifesto(
        selecionados, core_sintetico_sha256="a" * 64, alert_rules_version=1, mapping_version=1, seed=42
    )
    m2 = constroi_manifesto(
        selecionados, core_sintetico_sha256="a" * 64, alert_rules_version=1, mapping_version=1, seed=42
    )
    assert m1.manifest_sha256 == m2.manifest_sha256
    assert m1.contagem_por_estrato == {"Structuring": 1}


def test_constroi_manifesto_hash_muda_se_a_selecao_muda():
    base = constroi_manifesto(
        [(_alerta([_tx(1)]), "Structuring")],
        core_sintetico_sha256="a" * 64,
        alert_rules_version=1,
        mapping_version=1,
        seed=42,
    )
    outro_alerta = _alerta([_tx(1)])
    outro_alerta = outro_alerta.model_copy(update={"alert_id": uuid_mod.uuid4()})
    diferente = constroi_manifesto(
        [(outro_alerta, "Structuring")],
        core_sintetico_sha256="a" * 64,
        alert_rules_version=1,
        mapping_version=1,
        seed=42,
    )
    assert base.manifest_sha256 != diferente.manifest_sha256


def test_grava_e_carrega_manifesto_ida_e_volta(tmp_path):
    selecionados = [(_alerta([_tx(1)]), "Structuring")]
    manifesto = constroi_manifesto(
        selecionados, core_sintetico_sha256="a" * 64, alert_rules_version=1, mapping_version=1, seed=42
    )
    destino = tmp_path / "v1"
    grava_golden(destino, manifesto, selecionados)
    assert (destino / "manifest.json").exists()
    payload_files = list((destino / "payloads").glob("*.json"))
    assert len(payload_files) == 1
    recarregado = carrega_manifesto(destino / "manifest.json")
    assert recarregado == manifesto
    conteudo_payload = json.loads(payload_files[0].read_text(encoding="utf-8"))
    assert conteudo_payload["alert_id"] == str(selecionados[0][0].alert_id)
