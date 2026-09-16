"""Gerador de alertas do monitoramento legado simulado (T0.8): DT-01, `SPEC.md` §3.1, §8.3.

O banco é montado direto com `core_db` (sem passar pelo SAML-D) para controlar timestamps e rótulos com
precisão: os casos aqui testam a regra dos 45 dias, a validação DT-01 e o cálculo da taxa de falso positivo,
não a conversão da camada brasileira (já coberta em `test_camada_br*`).
"""

from __future__ import annotations

from contextlib import closing
from datetime import UTC, date, datetime, timedelta

import pytest

from aml_guardian.config._base import Aprovacao, Situacao
from aml_guardian.config.alert_rules import (
    AlertRulesConfig,
    ContagemVelocidade,
    RegrasLegado,
    ValorElevado,
    load_alert_rules,
)
from aml_guardian.contracts.ingestion import PaymentType, SyntheticCustomer, Transaction
from aml_guardian.sourcedata.alert_generator import (
    RULE_ID_CONTAGEM_VELOCIDADE,
    RULE_ID_VALOR_ELEVADO,
    calcula_falso_positivo,
    gera_alertas,
)
from aml_guardian.sourcedata.core_db import conecta, cria_schema, grava_clientes, grava_meta, grava_transacoes

_APROVACAO = Aprovacao(por="teste@teste.com", em=date(2026, 9, 16), situacao=Situacao.PROVISORIO, referencia="teste")


@pytest.fixture
def regras() -> AlertRulesConfig:
    """Limiares pequenos e independentes dos valores de produção, para deixar o cenário do teste legível."""
    return AlertRulesConfig(
        alert_rules_version=1,
        aprovacao=_APROVACAO,
        regras=RegrasLegado(
            valor_elevado=ValorElevado(descricao="teste", limiar_brl="10000.00", janela_agrupamento_dias=7),
            contagem_velocidade=ContagemVelocidade(descricao="teste", min_transacoes=3, janela_dias=10),
        ),
    )


def _tx(conta: str, indice: int, quando: datetime, valor: str) -> Transaction:
    return Transaction(
        transaction_id=f"tx-{conta}-{indice:04d}",
        timestamp=quando,
        amount_brl=valor,
        payment_type=PaymentType.PIX,
        sender_account=conta,
        receiver_account="9999-9999999-9",
        sender_location="BR",
        receiver_location="BR",
        currency_sent="BRL",
        currency_received="BRL",
    )


def _dia(ano: int, mes: int, dia: int) -> datetime:
    return datetime(ano, mes, dia, 12, 0, tzinfo=UTC)


@pytest.fixture
def banco(tmp_path) -> tuple[str, dict[str, list[tuple[Transaction, bool]]]]:
    """Três contas: `valor` (regra A, 2 episódios distantes), `velocidade` (regra B, 2 episódios), `normal` (0)."""
    cenario: dict[str, list[tuple[Transaction, bool]]] = {
        "conta-valor": [
            (_tx("conta-valor", 1, _dia(2023, 1, 10), "5000.00"), False),
            (_tx("conta-valor", 2, _dia(2023, 1, 12), "15000.00"), False),  # dispara A: episódio 1 (FP)
            (_tx("conta-valor", 3, _dia(2023, 4, 1), "20000.00"), True),  # dispara A: episódio 2, isolado (TP)
        ],
        "conta-velocidade": [
            (_tx("conta-velocidade", 1, _dia(2023, 2, 1), "100.00"), False),
            (_tx("conta-velocidade", 2, _dia(2023, 2, 5), "100.00"), False),
            (_tx("conta-velocidade", 3, _dia(2023, 2, 8), "100.00"), False),  # dispara B: episódio 1 (FP)
            (_tx("conta-velocidade", 4, _dia(2023, 6, 1), "100.00"), False),
            (_tx("conta-velocidade", 5, _dia(2023, 6, 3), "100.00"), True),
            (_tx("conta-velocidade", 6, _dia(2023, 6, 5), "100.00"), False),  # dispara B: episódio 2 (TP)
        ],
        "conta-normal": [
            (_tx("conta-normal", 1, _dia(2023, 3, 1), "500.00"), False),
            (_tx("conta-normal", 2, _dia(2023, 3, 20), "500.00"), False),
        ],
    }
    db = tmp_path / "core.sqlite"
    with closing(conecta(db)) as conn:
        cria_schema(conn)
        grava_clientes(
            conn,
            [
                SyntheticCustomer(
                    customer_id=f"CUST-{conta}",
                    name=f"Cliente {conta}",
                    cpf_cnpj=f"{indice:011d}",
                    accounts=[conta],
                    segment="PF",
                    restriction_flags=[],
                )
                for indice, conta in enumerate(cenario, start=1)
            ],
        )
        grava_transacoes(
            conn,
            [
                (transacao, "Structuring" if suspeita else "Normal_Fan_Out", suspeita)
                for lote in cenario.values()
                for transacao, suspeita in lote
            ],
        )
        grava_meta(conn, {"seed": "teste"})
        conn.commit()
    return db, cenario


def test_nenhum_alerta_com_ocorrencia_maior_que_45_dias(banco, regras):
    db, _ = banco
    alertas = gera_alertas(db_path=db, regras=regras)
    assert alertas
    for alerta in alertas:
        limite = alerta.selected_at - timedelta(days=45)
        for transacao in alerta.transactions:
            assert transacao.timestamp >= limite


def test_todo_alerta_valida_no_dt01_e_janela_coerente(banco, regras):
    db, _ = banco
    alertas = gera_alertas(db_path=db, regras=regras)
    for alerta in alertas:
        assert alerta.transactions
        assert alerta.occurrence_window.start <= alerta.occurrence_window.end
        assert alerta.occurrence_window.end <= alerta.selected_at
        assert all(t.sender_account == alerta.sender_account for t in alerta.transactions)


def test_regra_valor_elevado_gera_dois_episodios_separados(banco, regras):
    db, _ = banco
    alertas = [a for a in gera_alertas(db_path=db, regras=regras) if a.sender_account == "conta-valor"]
    assert len(alertas) == 2
    tamanhos = sorted(len(a.transactions) for a in alertas)
    assert tamanhos == [1, 2]  # episódio 1 agrupa tx1+tx2; episódio 2 só tx3 (fora da janela de 7 dias)


def test_regra_contagem_velocidade_gera_dois_episodios(banco, regras):
    db, _ = banco
    alertas = [a for a in gera_alertas(db_path=db, regras=regras) if a.sender_account == "conta-velocidade"]
    assert len(alertas) == 2
    for alerta in alertas:
        assert len(alerta.transactions) == 3
        assert alerta.source_rule_id == RULE_ID_CONTAGEM_VELOCIDADE


def test_conta_sem_gatilho_nao_gera_alerta(banco, regras):
    db, _ = banco
    alertas = [a for a in gera_alertas(db_path=db, regras=regras) if a.sender_account == "conta-normal"]
    assert alertas == []


def test_taxa_de_falso_positivo_calculada_e_reportada(banco, regras):
    db, _ = banco
    alertas = gera_alertas(db_path=db, regras=regras)
    relatorio = calcula_falso_positivo(alertas, db_path=db)

    assert relatorio.total_alertas == 4
    assert relatorio.falsos_positivos == 2
    assert relatorio.taxa_falso_positivo == pytest.approx(0.5)
    assert relatorio.por_regra[RULE_ID_VALOR_ELEVADO] == (2, 1)
    assert relatorio.por_regra[RULE_ID_CONTAGEM_VELOCIDADE] == (2, 1)


def test_alert_id_e_deterministico_para_o_mesmo_banco(banco, regras):
    db, _ = banco
    primeira = {a.alert_id for a in gera_alertas(db_path=db, regras=regras)}
    segunda = {a.alert_id for a in gera_alertas(db_path=db, regras=regras)}
    assert primeira == segunda
    assert len(primeira) == 4


def test_conta_sem_cliente_correspondente_e_ignorada(tmp_path, regras):
    """`transacoes.sender_account` sem linha correspondente em `contas`/`clientes` não derruba o gerador."""
    db = tmp_path / "orfa.sqlite"
    conta_orfa = "conta-orfa"
    with closing(conecta(db)) as conn:
        cria_schema(conn)
        grava_clientes(conn, [])
        grava_transacoes(
            conn,
            [(_tx(conta_orfa, 1, _dia(2023, 1, 10), "999999.00"), "Normal_Fan_Out", False)],
        )
        grava_meta(conn, {"seed": "teste-orfa"})
        conn.commit()

    alertas = gera_alertas(db_path=db, regras=regras)
    assert alertas == []


def test_config_de_producao_carrega():
    config = load_alert_rules()
    assert config.alert_rules_version == 1
    assert config.regras.valor_elevado.limiar_brl > 0
    assert config.regras.contagem_velocidade.min_transacoes >= 2
