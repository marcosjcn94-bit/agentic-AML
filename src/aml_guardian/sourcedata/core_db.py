"""Esquema e gravação de `data/core_sintetico.sqlite` (T0.7, SPEC.md §8.1).

O banco simula o sistema de origem da instituição: contém dado pessoal sintético (DT-03) e as transações
(DT-02). É o único lugar do projeto onde documento e nome existem em claro — nada aqui pode ser copiado para
`app.sqlite`, prompt, log ou coleção vetorial sem passar pelo sanitizador (RF-01, RF-02).

O arquivo não é versionado (`.gitignore`: `*.sqlite`) e é reconstruível a partir do SAML-D com a mesma seed.
Valores monetários são gravados como TEXT decimal exato, nunca REAL, para não perder centavo em binário.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable, Mapping
from pathlib import Path

from aml_guardian.contracts.ingestion import SyntheticCustomer, Transaction

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
CORE_DB_FILE = "core_sintetico.sqlite"
CORE_DB_PATH = DATA_DIR / CORE_DB_FILE

SCHEMA = """
CREATE TABLE clientes (
    customer_id       TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    cpf_cnpj          TEXT NOT NULL UNIQUE,
    segment           TEXT NOT NULL,
    restriction_flags TEXT NOT NULL
);
CREATE TABLE contas (
    conta       TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES clientes(customer_id)
);
CREATE TABLE transacoes (
    transaction_id    TEXT PRIMARY KEY,
    timestamp         TEXT NOT NULL,
    amount_brl        TEXT NOT NULL,
    payment_type      TEXT NOT NULL,
    sender_account    TEXT NOT NULL,
    receiver_account  TEXT NOT NULL,
    sender_location   TEXT NOT NULL,
    receiver_location TEXT NOT NULL,
    currency_sent     TEXT NOT NULL,
    currency_received TEXT NOT NULL,
    laundering_type   TEXT NOT NULL,
    is_laundering     INTEGER NOT NULL CHECK (is_laundering IN (0, 1))
);
CREATE INDEX idx_transacoes_remetente ON transacoes (sender_account, timestamp);
CREATE INDEX idx_transacoes_rotulo ON transacoes (laundering_type);
CREATE TABLE meta (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);
"""

#: Consultas do hash de conteúdo, em ordem fixa e determinística. `meta` fica de fora de propósito: o hash
#: compara o CONTEÚDO de dois bancos, e a proveniência (seed, versões) mudaria o hash sem mudar os dados.
_CONSULTAS_HASH = (
    "SELECT customer_id, name, cpf_cnpj, segment, restriction_flags FROM clientes ORDER BY customer_id",
    "SELECT conta, customer_id FROM contas ORDER BY conta",
    """SELECT transaction_id, timestamp, amount_brl, payment_type, sender_account, receiver_account,
              sender_location, receiver_location, currency_sent, currency_received, laundering_type, is_laundering
       FROM transacoes ORDER BY transaction_id""",
)


def conecta(path: Path) -> sqlite3.Connection:
    """Abre a conexão com integridade referencial ligada (não é o padrão do SQLite)."""
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def cria_schema(conn: sqlite3.Connection) -> None:
    """Cria as tabelas do zero; falha se o banco já tiver esquema, para nunca mesclar duas gerações."""
    conn.executescript(SCHEMA)


def grava_clientes(conn: sqlite3.Connection, clientes: Iterable[SyntheticCustomer]) -> int:
    """Grava os DT-03 e as contas de cada um; devolve quantos clientes foram gravados."""
    total = 0
    for cliente in clientes:
        conn.execute(
            "INSERT INTO clientes (customer_id, name, cpf_cnpj, segment, restriction_flags) VALUES (?, ?, ?, ?, ?)",
            (
                cliente.customer_id,
                cliente.name,
                cliente.cpf_cnpj,
                cliente.segment,
                json.dumps(cliente.restriction_flags),
            ),
        )
        conn.executemany(
            "INSERT INTO contas (conta, customer_id) VALUES (?, ?)",
            [(conta, cliente.customer_id) for conta in cliente.accounts],
        )
        total += 1
    return total


def grava_transacoes(conn: sqlite3.Connection, transacoes: Iterable[tuple[Transaction, str, bool]]) -> int:
    """Grava os DT-02 com o rótulo de tipologia do SAML-D preservado; devolve quantas foram gravadas."""
    total = 0
    for transacao, rotulo, suspeita in transacoes:
        conn.execute(
            """INSERT INTO transacoes (transaction_id, timestamp, amount_brl, payment_type, sender_account,
                                       receiver_account, sender_location, receiver_location, currency_sent,
                                       currency_received, laundering_type, is_laundering)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                transacao.transaction_id,
                transacao.timestamp.isoformat(),
                str(transacao.amount_brl),
                transacao.payment_type.value,
                transacao.sender_account,
                transacao.receiver_account,
                transacao.sender_location,
                transacao.receiver_location,
                transacao.currency_sent,
                transacao.currency_received,
                rotulo,
                int(suspeita),
            ),
        )
        total += 1
    return total


def grava_meta(conn: sqlite3.Connection, dados: Mapping[str, object]) -> None:
    """Grava a proveniência da geração (seed e versões de configuração) em `meta`."""
    conn.executemany(
        "INSERT OR REPLACE INTO meta (chave, valor) VALUES (?, ?)",
        [(chave, str(valor)) for chave, valor in dados.items()],
    )


def conteudo_sha256(conn: sqlite3.Connection) -> str:
    """SHA-256 do conteúdo das tabelas de dados, em ordem fixa — evidência de que a seed reproduz o banco."""
    digest = hashlib.sha256()
    for consulta in _CONSULTAS_HASH:
        for linha in conn.execute(consulta):
            campos = ("" if valor is None else str(valor) for valor in linha)
            digest.update(("\x1f".join(campos) + "\x1e").encode("utf-8"))
    return digest.hexdigest()
