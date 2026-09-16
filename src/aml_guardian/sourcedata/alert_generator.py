"""Gerador de alertas do monitoramento legado SIMULADO sobre `core_sintetico` (T0.8).

IDs: DT-01, `SPEC.md` §3.1 (Circ. 3.978/2020, art. 39, parágrafo único), §8.3.

Duas regras ingênuas e clássicas de sistema legado (`config/alert_rules.yaml`), aplicadas por conta remetente:
  - **valor_elevado:** transação isolada acima de um limiar em BRL;
  - **contagem_velocidade:** N ou mais transações em janela móvel, qualquer valor.

O objetivo é RUÍDO, não precisão: o `SPEC.md` §8.3 espera taxa de falso positivo na faixa 90-95% (INTENT), para
que os alertas sirvam de entrada realista à triagem determinística (T1.4) avaliar depois. `is_laundering` (rótulo
do SAML-D) nunca entra no DT-01 gerado — é usado só pelo relatório de falso positivo, fora do contrato do alerta,
porque o próprio sistema legado real não teria acesso ao rótulo verdadeiro.

Cada episódio contínuo de gatilhos (gatilhos a `janela` ou menos um do outro) vira 1 alerta, com
`occurrence_window` limitado à janela da regra (≤ 30 dias) — nunca cresce indefinidamente, o que manteria a
regra dos 45 dias (Circ. 3.978/2020, art. 39, parágrafo único) satisfeita por construção.
"""

from __future__ import annotations

import sqlite3
import uuid
from collections import deque
from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from aml_guardian.config.alert_rules import AlertRulesConfig, ContagemVelocidade, ValorElevado, load_alert_rules
from aml_guardian.contracts.ingestion import Alert, OccurrenceWindow, PaymentType, SenderCustomer, Transaction
from aml_guardian.sourcedata.core_db import CORE_DB_PATH, conecta

#: Namespace fixo para `alert_id` determinístico (uuid5): mesmo `core_sintetico` → mesmos alertas.
_NAMESPACE_ALERTAS = uuid.UUID("6f1b1d8a-9b3e-4c7a-8f2e-2a9c7d4b5e10")

RULE_ID_VALOR_ELEVADO = "LEG-VALOR-ELEVADO-01"
RULE_ID_CONTAGEM_VELOCIDADE = "LEG-CONTAGEM-VELOC-01"


@dataclass(frozen=True)
class _Episodio:
    regra: str
    inicio: datetime
    fim: datetime


@dataclass(frozen=True)
class RelatorioFalsoPositivo:
    """Taxa de falso positivo do lote de alertas gerado (`SPEC.md` §8.3: faixa 90-95%, INTENT)."""

    total_alertas: int
    falsos_positivos: int
    por_regra: dict[str, tuple[int, int]] = field(default_factory=dict)  # rule_id -> (total, falsos_positivos)

    @property
    def taxa_falso_positivo(self) -> float:
        if self.total_alertas == 0:
            return 0.0
        return self.falsos_positivos / self.total_alertas


def _transacoes_por_conta(conn: sqlite3.Connection) -> Iterator[tuple[str, list[Transaction]]]:
    """Uma entrada por conta remetente, transações em ordem de tempo (a tabela já é indexada assim)."""
    conn.row_factory = sqlite3.Row
    conta_atual: str | None = None
    lote: list[Transaction] = []
    for linha in conn.execute(
        """SELECT sender_account, transaction_id, timestamp, amount_brl, payment_type, receiver_account,
                  sender_location, receiver_location, currency_sent, currency_received
           FROM transacoes ORDER BY sender_account, timestamp"""
    ):
        if linha["sender_account"] != conta_atual:
            if conta_atual is not None:
                yield conta_atual, lote
            conta_atual = linha["sender_account"]
            lote = []
        lote.append(
            Transaction(
                transaction_id=linha["transaction_id"],
                timestamp=datetime.fromisoformat(linha["timestamp"]),
                amount_brl=linha["amount_brl"],
                payment_type=PaymentType(linha["payment_type"]),
                sender_account=linha["sender_account"],
                receiver_account=linha["receiver_account"],
                sender_location=linha["sender_location"],
                receiver_location=linha["receiver_location"],
                currency_sent=linha["currency_sent"],
                currency_received=linha["currency_received"],
            )
        )
    if conta_atual is not None:
        yield conta_atual, lote


def _clientes_por_conta(conn: sqlite3.Connection) -> dict[str, SenderCustomer]:
    conn.row_factory = sqlite3.Row
    return {
        linha["conta"]: SenderCustomer(name=linha["name"], cpf_cnpj=linha["cpf_cnpj"])
        for linha in conn.execute(
            "SELECT contas.conta AS conta, clientes.name, clientes.cpf_cnpj "
            "FROM contas JOIN clientes USING (customer_id)"
        )
    }


def _gatilhos_valor_elevado(transacoes: list[Transaction], regra: ValorElevado) -> list[datetime]:
    return [t.timestamp for t in transacoes if t.amount_brl >= regra.limiar_brl]


def _gatilhos_contagem_velocidade(transacoes: list[Transaction], regra: ContagemVelocidade) -> list[datetime]:
    janela = timedelta(days=regra.janela_dias)
    buffer: deque[datetime] = deque()
    gatilhos: list[datetime] = []
    for t in transacoes:
        buffer.append(t.timestamp)
        while buffer[0] < t.timestamp - janela:
            buffer.popleft()
        if len(buffer) >= regra.min_transacoes:
            gatilhos.append(t.timestamp)
    return gatilhos


def _fim_de_episodio(momentos: list[datetime], janela: timedelta) -> list[datetime]:
    """Momento do ÚLTIMO gatilho de cada episódio contínuo (gatilhos a <= `janela` um do outro).

    Impede que episódios cresçam sem limite: o `occurrence_window` de cada alerta fica sempre <= `janela`.
    """
    ordenados = sorted(momentos)
    fins: list[datetime] = []
    for indice, momento in enumerate(ordenados):
        seguinte = ordenados[indice + 1] if indice + 1 < len(ordenados) else None
        if seguinte is None or seguinte - momento > janela:
            fins.append(momento)
    return fins


def _episodios(
    regra_id: str, transacoes: list[Transaction], gatilhos: list[datetime], janela: timedelta
) -> list[_Episodio]:
    """`incluidas` nunca fica vazia: `fim` vem sempre de `gatilhos`, e todo gatilho é o `timestamp` de
    alguma transação em `transacoes` — logo essa transação sempre cai dentro de `[fim - janela, fim]`."""
    episodios = []
    for fim in _fim_de_episodio(gatilhos, janela):
        inicio_janela = fim - janela
        incluidas = [t.timestamp for t in transacoes if inicio_janela <= t.timestamp <= fim]
        episodios.append(_Episodio(regra=regra_id, inicio=min(incluidas), fim=fim))
    return episodios


def _monta_alerta(
    conta: str,
    cliente: SenderCustomer,
    transacoes: list[Transaction],
    episodio: _Episodio,
) -> Alert:
    incluidas = [t for t in transacoes if episodio.inicio <= t.timestamp <= episodio.fim]
    alert_id = uuid.uuid5(
        _NAMESPACE_ALERTAS, f"{conta}|{episodio.regra}|{episodio.inicio.isoformat()}|{episodio.fim.isoformat()}"
    )
    return Alert(
        alert_id=alert_id,
        source_rule_id=episodio.regra,
        selected_at=episodio.fim,
        occurrence_window=OccurrenceWindow(start=episodio.inicio, end=episodio.fim),
        sender_account=conta,
        sender_customer=cliente,
        transactions=incluidas,
    )


def gera_alertas(db_path: Path | None = None, regras: AlertRulesConfig | None = None) -> list[Alert]:
    """Aplica as duas regras do monitoramento legado sobre `core_sintetico`; devolve todos os alertas gerados."""
    caminho = db_path or CORE_DB_PATH
    config = regras or load_alert_rules()
    janela_valor = timedelta(days=config.regras.valor_elevado.janela_agrupamento_dias)
    janela_contagem = timedelta(days=config.regras.contagem_velocidade.janela_dias)

    alertas: list[Alert] = []
    with closing(conecta(caminho)) as conn:
        clientes = _clientes_por_conta(conn)
        for conta, transacoes in _transacoes_por_conta(conn):
            cliente = clientes.get(conta)
            if cliente is None:
                # `transacoes.sender_account` não tem FK para `contas.conta`: uma conta remetente sem
                # cliente cadastrado é ignorada, como faria um legado real sem dados para compor o alerta.
                continue
            gatilhos_valor = _gatilhos_valor_elevado(transacoes, config.regras.valor_elevado)
            for episodio in _episodios(RULE_ID_VALOR_ELEVADO, transacoes, gatilhos_valor, janela_valor):
                alertas.append(_monta_alerta(conta, cliente, transacoes, episodio))

            gatilhos_contagem = _gatilhos_contagem_velocidade(transacoes, config.regras.contagem_velocidade)
            for episodio in _episodios(RULE_ID_CONTAGEM_VELOCIDADE, transacoes, gatilhos_contagem, janela_contagem):
                alertas.append(_monta_alerta(conta, cliente, transacoes, episodio))
    return alertas


def calcula_falso_positivo(alertas: list[Alert], db_path: Path | None = None) -> RelatorioFalsoPositivo:
    """Um alerta é falso positivo quando NENHUMA transação incluída é rotulada suspeita no `core_sintetico`.

    O rótulo `is_laundering` só existe no `core_sintetico` (dado de avaliação, nunca no DT-01): um sistema de
    monitoramento legado real não teria acesso a ele.
    """
    caminho = db_path or CORE_DB_PATH
    with closing(conecta(caminho)) as conn:
        rotulos = dict(conn.execute("SELECT transaction_id, is_laundering FROM transacoes"))

    total_por_regra: dict[str, list[int]] = {}
    falsos_positivos = 0
    for alerta in alertas:
        suspeito = any(rotulos[t.transaction_id] for t in alerta.transactions)
        contadores = total_por_regra.setdefault(alerta.source_rule_id, [0, 0])
        contadores[0] += 1
        if not suspeito:
            falsos_positivos += 1
            contadores[1] += 1

    return RelatorioFalsoPositivo(
        total_alertas=len(alertas),
        falsos_positivos=falsos_positivos,
        por_regra={regra: (total, fp) for regra, (total, fp) in total_por_regra.items()},
    )
