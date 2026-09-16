"""Fixtures da camada brasileira (T0.7), compartilhadas entre os arquivos `test_camada_br*`.

O CSV é montado aqui com os rótulos exatos do SAML-D: nenhum caso toca o arquivo real, que não é versionado
(CC BY-NC-SA 4.0) e tem 9,5 milhões de linhas.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aml_guardian.config.cambio import load_cambio
from aml_guardian.sourcedata.br_mapping import load_br_mapping
from aml_guardian.sourcedata.brazil_layer import SEED_PADRAO, constroi_core

COLUNAS = (
    "Time",
    "Date",
    "Sender_account",
    "Receiver_account",
    "Amount",
    "Payment_currency",
    "Received_currency",
    "Sender_bank_location",
    "Receiver_bank_location",
    "Payment_type",
    "Is_laundering",
    "Laundering_type",
)


def _linha(
    conta: str,
    recebedor: str = "2769355426",
    amount: str = "1459.15",
    moeda: str = "UK pounds",
    local: str = "UK",
    destino: str = "UK",
    tipo: str = "Cash Deposit",
    flag: str = "0",
    rotulo: str = "Normal_Cash_Deposits",
    hora: str = "10:35:19",
    data: str = "2022-10-07",
) -> tuple[str, ...]:
    return (hora, data, conta, recebedor, amount, moeda, moeda, local, destino, tipo, flag, rotulo)


def _csv(destino: Path, linhas: tuple[tuple[str, ...], ...]) -> Path:
    corpo = [",".join(COLUNAS), *(",".join(linha) for linha in linhas)]
    destino.write_text("\n".join(corpo) + "\n", encoding="utf-8")
    return destino


@pytest.fixture(scope="module")
def cambio():
    return load_cambio()


@pytest.fixture(scope="module")
def br():
    return load_br_mapping()


@pytest.fixture
def csv_base(tmp_path) -> Path:
    """CSV pequeno com conta suspeita, contas normais, moeda estrangeira e envio ao exterior."""
    linhas = (
        _linha("1000000001", amount="9500.00", tipo="Cash Deposit", flag="1", rotulo="Structuring"),
        _linha("1000000001", amount="9400.00", tipo="Cash Deposit", flag="1", rotulo="Structuring"),
        _linha("1000000001", amount="8000.00", tipo="Cross-border", destino="Germany", flag="1", rotulo="Structuring"),
        _linha("2000000002", amount="120.00", tipo="ACH"),
        _linha("2000000002", amount="340.50", tipo="Cheque"),
        _linha("3000000003", amount="10.47", moeda="Yen", local="Japan", destino="Japan", tipo="Debit card"),
        _linha("4000000004", amount="13.91", moeda="Naira", local="Nigeria", destino="Nigeria", tipo="Credit card"),
        _linha("5000000005", amount="770.00", tipo="Cash Withdrawal"),
    )
    return _csv(tmp_path / "saml.csv", linhas)


@pytest.fixture
def core(csv_base, tmp_path):
    """Banco gerado a partir do CSV sintético, com todas as contas incluídas."""
    db = tmp_path / "core.sqlite"
    relatorio = constroi_core(csv_path=csv_base, db_path=db, seed=SEED_PADRAO, contas_normais=10)
    return db, relatorio
