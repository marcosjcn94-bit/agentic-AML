"""Conteúdo do `core_sintetico.sqlite` e determinismo por seed (T0.7): SPEC.md §8.1, RNF-09, DT-02 e DT-03.

As fixtures do CSV sintético e do banco ficam em `conftest.py`; o câmbio e o mapeamento, em `test_camada_br.py`.
"""

from __future__ import annotations

import sqlite3

import yaml

from aml_guardian.contracts.ingestion import SyntheticCustomer, Transaction
from aml_guardian.sourcedata.brazil_layer import CONTAS_NORMAIS_PADRAO, SEED_PADRAO, constroi_core
from aml_guardian.sourcedata.core_db import conteudo_sha256

# --- Banco gerado: conteúdo e contratos ---


def test_core_grava_transacoes_e_clientes(core):
    _, relatorio = core
    assert relatorio.transacoes == 8
    assert relatorio.contas == 5
    assert relatorio.clientes == 5
    assert relatorio.suspeitas == 3


def test_toda_transacao_do_banco_valida_no_dt02(core):
    db, _ = core
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        linhas = conn.execute("SELECT * FROM transacoes").fetchall()
    assert len(linhas) == 8
    for linha in linhas:
        transacao = Transaction.model_validate(
            {
                "transaction_id": linha["transaction_id"],
                "timestamp": linha["timestamp"],
                "amount_brl": linha["amount_brl"],
                "payment_type": linha["payment_type"],
                "sender_account": linha["sender_account"],
                "receiver_account": linha["receiver_account"],
                "sender_location": linha["sender_location"],
                "receiver_location": linha["receiver_location"],
                "currency_sent": linha["currency_sent"],
                "currency_received": linha["currency_received"],
            }
        )
        assert transacao.amount_brl > 0


def test_todo_cliente_do_banco_valida_no_dt03(core):
    db, _ = core
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        clientes = conn.execute("SELECT * FROM clientes").fetchall()
        contas = conn.execute("SELECT customer_id, conta FROM contas").fetchall()
    por_cliente: dict[str, list[str]] = {}
    for conta in contas:
        por_cliente.setdefault(conta["customer_id"], []).append(conta["conta"])
    for cliente in clientes:
        SyntheticCustomer.model_validate(
            {
                "customer_id": cliente["customer_id"],
                "name": cliente["name"],
                "cpf_cnpj": cliente["cpf_cnpj"],
                "accounts": por_cliente[cliente["customer_id"]],
                "segment": cliente["segment"],
                "restriction_flags": yaml.safe_load(cliente["restriction_flags"]),
            }
        )


def test_conversao_de_moeda_e_pais_chega_ao_banco(core):
    db, _ = core
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        pix = conn.execute("SELECT * FROM transacoes WHERE payment_type = 'PIX'").fetchone()
        exterior = conn.execute("SELECT * FROM transacoes WHERE receiver_location != 'BR'").fetchall()
    assert pix["currency_sent"] == "GBP"
    assert pix["sender_location"] == "BR"
    assert pix["amount_brl"] == "744.00"
    assert {linha["receiver_location"] for linha in exterior} == {"DE", "JP", "NG"}


def test_rotulo_de_tipologia_e_preservado_para_o_golden_set(core):
    db, _ = core
    with sqlite3.connect(db) as conn:
        rotulos = dict(conn.execute("SELECT laundering_type, COUNT(*) FROM transacoes GROUP BY 1").fetchall())
    assert rotulos["Structuring"] == 3
    assert rotulos["Normal_Cash_Deposits"] == 5


def test_proveniencia_fica_gravada_em_meta(core):
    db, _ = core
    with sqlite3.connect(db) as conn:
        meta = dict(conn.execute("SELECT chave, valor FROM meta").fetchall())
    assert meta["seed"] == str(SEED_PADRAO)
    assert meta["cambio_version"] == "1"
    assert meta["br_mapping_version"] == "1"


# --- Determinismo por seed (SPEC.md RNF-09) ---


def test_mesma_seed_reproduz_o_mesmo_banco(csv_base, tmp_path):
    hashes = []
    for nome in ("a.sqlite", "b.sqlite"):
        db = tmp_path / nome
        constroi_core(csv_path=csv_base, db_path=db, seed=SEED_PADRAO, contas_normais=10)
        with sqlite3.connect(db) as conn:
            hashes.append(conteudo_sha256(conn))
    assert hashes[0] == hashes[1]


def test_seed_diferente_muda_o_conteudo(csv_base, tmp_path):
    hashes = []
    for nome, seed in (("a.sqlite", SEED_PADRAO), ("b.sqlite", SEED_PADRAO + 1)):
        db = tmp_path / nome
        constroi_core(csv_path=csv_base, db_path=db, seed=seed, contas_normais=10)
        with sqlite3.connect(db) as conn:
            hashes.append(conteudo_sha256(conn))
    assert hashes[0] != hashes[1]


def test_transaction_id_nao_depende_da_amostra(csv_base, tmp_path):
    """O id é a posição da linha no CSV: a mesma transação tem o mesmo id em qualquer amostra."""
    ids = []
    for nome, contas_normais in (("todas.sqlite", 10), ("so_suspeita.sqlite", 0)):
        db = tmp_path / nome
        constroi_core(csv_path=csv_base, db_path=db, seed=SEED_PADRAO, contas_normais=contas_normais)
        with sqlite3.connect(db) as conn:
            ids.append({linha[0] for linha in conn.execute("SELECT transaction_id FROM transacoes")})
    assert ids[1] < ids[0]
    assert ids[1] == {"tx-00000001", "tx-00000002", "tx-00000003"}


def test_amostra_mantem_todas_as_contas_com_suspeita(csv_base, tmp_path):
    """Contas com transação suspeita entram inteiras, mesmo com orçamento de contas normais igual a zero."""
    db = tmp_path / "core.sqlite"
    relatorio = constroi_core(csv_path=csv_base, db_path=db, seed=SEED_PADRAO, contas_normais=0)
    with sqlite3.connect(db) as conn:
        contas = {linha[0] for linha in conn.execute("SELECT DISTINCT sender_account FROM transacoes")}
        suspeitas = conn.execute("SELECT COUNT(*) FROM transacoes WHERE is_laundering = 1").fetchone()[0]
    assert relatorio.contas == 1
    assert len(contas) == 1
    assert suspeitas == 3


def test_banco_e_recriado_do_zero_e_nunca_completado(csv_base, tmp_path):
    """Gerar duas vezes no mesmo caminho não duplica linha: o arquivo anterior é substituído."""
    db = tmp_path / "core.sqlite"
    constroi_core(csv_path=csv_base, db_path=db, seed=SEED_PADRAO, contas_normais=10)
    constroi_core(csv_path=csv_base, db_path=db, seed=SEED_PADRAO, contas_normais=10)
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM transacoes").fetchone()[0] == 8


def test_padrao_de_contas_normais_e_explicito():
    assert CONTAS_NORMAIS_PADRAO > 0
    assert SEED_PADRAO > 0
