"""Camada brasileira: SAML-D → DT-02/DT-03 e gravação do `core_sintetico.sqlite` (T0.7, SPEC.md §8.1, §8.3).

Três conversões, todas governadas por dado versionado (nunca por regra implícita em código):
  - valor → BRL pela taxa fixa sintética de `config/cambio.yaml`, e moeda → ISO-4217 do DT-02;
  - `Payment_type` e localização bancária → domínio do DT-02 por `data/mappings/saml_d_to_br.yaml`;
  - conta remetente → cliente sintético (DT-03) com CPF/CNPJ de DV válido gerado pela seed.

A base real tem 9,5 milhões de linhas e 292.715 contas remetentes. A amostra é POR CONTA, não por linha: quando
uma conta entra, entram todas as suas transações, porque o gerador de alertas da T0.8 aplica regras de janela
móvel por conta remetente e uma amostra de linhas soltas destruiria esses padrões. Toda conta com transação
suspeita entra, para que nenhuma tipologia rotulada se perca antes do golden set da T0.9.
"""

from __future__ import annotations

import random
from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import get_args

from aml_guardian.config.cambio import CambioConfig, load_cambio
from aml_guardian.config.triage import ListaRestricao
from aml_guardian.contracts.ingestion import SyntheticCustomer, Transaction
from aml_guardian.contracts.runtime import BRASILIA
from aml_guardian.sourcedata.br_mapping import BrMapping, load_br_mapping
from aml_guardian.sourcedata.core_db import (
    CORE_DB_PATH,
    conecta,
    cria_schema,
    grava_clientes,
    grava_meta,
    grava_transacoes,
)
from aml_guardian.sourcedata.documentos import conta_bancaria, gera_documentos
from aml_guardian.sourcedata.mapping import SamlDMapping, load_saml_d_mapping
from aml_guardian.sourcedata.saml_loader import RAW_DIR, SAML_D_FILE, iter_transactions

#: Seed do aceite da T0.7. Mudar a seed muda todo documento, nome e amostra — e o hash do banco.
SEED_PADRAO = 20260916

#: Contas remetentes normais sorteadas além das 4.950 que têm transação suspeita: chega a ~1 milhão de linhas.
CONTAS_NORMAIS_PADRAO = 8000

#: Proporção de clientes pessoa jurídica (CNPJ); os demais são pessoa física (CPF).
PROPORCAO_PJ = 0.2

#: Frequência de cada lista de restrição sintética. Valores provisórios da PoC: não representam a incidência
#: real de PEP, CEIS ou CNEP na população, e nenhuma lista real é usada (gate de saída do M0).
FREQUENCIA_LISTAS = {"pep": 0.01, "ceis": 0.005, "cnep": 0.005}

#: Partículas de nome sintético. Nenhuma pessoa real: a combinação é sorteada pela seed.
_PRENOMES = ("Ana", "Bruno", "Carla", "Diego", "Elisa", "Fábio", "Gisele", "Heitor", "Íris", "João")
_SOBRENOMES = ("Almeida", "Barbosa", "Carvalho", "Dias", "Esteves", "Farias", "Gomes", "Horta", "Ipiranga", "Jardim")
_RAZAO_SOCIAL = ("Comercial", "Distribuidora", "Importadora", "Logística", "Serviços")
_SUFIXO_PJ = ("LTDA", "ME", "EIRELI", "S/A")

LISTAS_RESTRICAO: tuple[str, ...] = get_args(ListaRestricao)


@dataclass(frozen=True)
class CoreReport:
    """Resumo da geração, usado como evidência de execução sobre o SAML-D real."""

    contas: int
    clientes: int
    transacoes: int
    suspeitas: int
    linhas_lidas: int
    rotulos: dict[str, int] = field(default_factory=dict)


def _contas_por_situacao(csv_path: Path, mapping: SamlDMapping) -> tuple[set[str], set[str]]:
    """Primeira passada: separa as contas remetentes com transação suspeita das puramente normais."""
    suspeitas: set[str] = set()
    normais: set[str] = set()
    for linha in iter_transactions(csv_path, mapping):
        conta = linha["Sender_account"]
        if mapping.is_suspeito(linha[_coluna_tipo(linha)]):
            suspeitas.add(conta)
        else:
            normais.add(conta)
    return suspeitas, normais - suspeitas


def _coluna_tipo(linha: dict[str, str]) -> str:
    """Nome efetivo da coluna de tipologia nesta linha (`Laundering_type` ou `Type`, SPEC.md §8.3)."""
    return "Laundering_type" if "Laundering_type" in linha else "Type"


def seleciona_contas(csv_path: Path, mapping: SamlDMapping, seed: int, contas_normais: int) -> frozenset[str]:
    """Contas remetentes do banco: todas as que têm suspeita, mais uma amostra determinística das normais."""
    if contas_normais < 0:
        raise ValueError(f"contas_normais negativo: {contas_normais}")
    com_suspeita, sem_suspeita = _contas_por_situacao(csv_path, mapping)
    candidatas = sorted(sem_suspeita)
    rng = random.Random(seed)
    sorteadas = candidatas if contas_normais >= len(candidatas) else rng.sample(candidatas, contas_normais)
    return frozenset(com_suspeita | set(sorteadas))


def _clientes(contas: frozenset[str], seed: int) -> list[SyntheticCustomer]:
    """Um DT-03 por conta remetente, com documento de DV válido e listas de restrição sintéticas."""
    ordenadas = sorted(contas)
    rng = random.Random(seed)
    juridicas = [rng.random() < PROPORCAO_PJ for _ in ordenadas]
    documentos = {
        True: iter(gera_documentos(rng, sum(juridicas), pessoa_juridica=True)),
        False: iter(gera_documentos(rng, len(ordenadas) - sum(juridicas), pessoa_juridica=False)),
    }
    clientes: list[SyntheticCustomer] = []
    for indice, (conta, pessoa_juridica) in enumerate(zip(ordenadas, juridicas, strict=True), start=1):
        flags = [lista for lista in LISTAS_RESTRICAO if rng.random() < FREQUENCIA_LISTAS[lista]]
        if pessoa_juridica:
            nome = f"{rng.choice(_RAZAO_SOCIAL)} {rng.choice(_SOBRENOMES)} {rng.choice(_SUFIXO_PJ)}"
        else:
            nome = f"{rng.choice(_PRENOMES)} {rng.choice(_SOBRENOMES)}"
        clientes.append(
            SyntheticCustomer(
                customer_id=f"CUST-{indice:07d}",
                name=nome,
                cpf_cnpj=next(documentos[pessoa_juridica]),
                accounts=[conta_bancaria(conta)],
                segment="PJ" if pessoa_juridica else "PF",
                restriction_flags=flags,
            )
        )
    return clientes


def para_transacao(linha: dict[str, str], indice: int, cambio: CambioConfig, br: BrMapping) -> Transaction:
    """Converte uma linha do SAML-D no DT-02, aplicando câmbio, meio de pagamento e país da camada brasileira.

    `indice` é a posição da linha no CSV: o `transaction_id` não depende da amostra, então a mesma transação tem
    o mesmo identificador em qualquer geração sobre o mesmo arquivo.
    """
    momento = datetime.strptime(f"{linha['Date']} {linha['Time']}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=BRASILIA)
    return Transaction(
        transaction_id=f"tx-{indice:08d}",
        timestamp=momento,
        amount_brl=cambio.converte(linha["Amount"], linha["Payment_currency"]),
        payment_type=br.payment_type(linha["Payment_type"]),
        sender_account=conta_bancaria(linha["Sender_account"]),
        receiver_account=conta_bancaria(linha["Receiver_account"]),
        sender_location=br.pais(linha["Sender_bank_location"]),
        receiver_location=br.pais(linha["Receiver_bank_location"]),
        currency_sent=cambio.iso(linha["Payment_currency"]),
        currency_received=cambio.iso(linha["Received_currency"]),
    )


def _transacoes(
    csv_path: Path,
    contas: frozenset[str],
    mapping: SamlDMapping,
    cambio: CambioConfig,
    br: BrMapping,
    contagem: dict[str, int],
) -> Iterator[tuple[Transaction, str, bool]]:
    """Segunda passada: converte apenas as linhas das contas selecionadas, preservando o rótulo de tipologia."""
    for indice, linha in enumerate(iter_transactions(csv_path, mapping), start=1):
        contagem["linhas"] += 1
        if linha["Sender_account"] not in contas:
            continue
        rotulo = linha[_coluna_tipo(linha)]
        contagem[rotulo] = contagem.get(rotulo, 0) + 1
        yield para_transacao(linha, indice, cambio, br), rotulo, mapping.is_suspeito(rotulo)


def constroi_core(
    csv_path: Path | None = None,
    db_path: Path | None = None,
    seed: int = SEED_PADRAO,
    contas_normais: int = CONTAS_NORMAIS_PADRAO,
    mapping: SamlDMapping | None = None,
    cambio: CambioConfig | None = None,
    br: BrMapping | None = None,
) -> CoreReport:
    """Gera `core_sintetico.sqlite` a partir do SAML-D; devolve o resumo do que foi gravado.

    O banco é sempre criado do zero: um arquivo preexistente é substituído, nunca completado, para que a seed
    descreva sozinha todo o conteúdo.
    """
    origem = csv_path or RAW_DIR / SAML_D_FILE
    destino = db_path or CORE_DB_PATH
    tipologias = mapping or load_saml_d_mapping()
    taxas = cambio or load_cambio()
    camada = br or load_br_mapping()

    contas = seleciona_contas(origem, tipologias, seed, contas_normais)
    clientes = _clientes(contas, seed)
    contagem: dict[str, int] = {"linhas": 0}

    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.unlink(missing_ok=True)
    # `closing`, e não o gerenciador do sqlite3: aquele faz commit mas NÃO fecha a conexão, e no Windows o
    # arquivo continua bloqueado — a geração seguinte no mesmo caminho falharia ao apagar o banco anterior.
    with closing(conecta(destino)) as conn:
        cria_schema(conn)
        total_clientes = grava_clientes(conn, clientes)
        total_transacoes = grava_transacoes(conn, _transacoes(origem, contas, tipologias, taxas, camada, contagem))
        suspeitas = conn.execute("SELECT COUNT(*) FROM transacoes WHERE is_laundering = 1").fetchone()[0]
        grava_meta(
            conn,
            {
                "seed": seed,
                "contas_normais": contas_normais,
                "cambio_version": taxas.cambio_version,
                "br_mapping_version": camada.br_mapping_version,
                "mapping_version": tipologias.mapping_version,
                "origem": origem.name,
            },
        )
        conn.commit()

    linhas_lidas = contagem.pop("linhas")
    return CoreReport(
        contas=len(contas),
        clientes=total_clientes,
        transacoes=total_transacoes,
        suspeitas=suspeitas,
        linhas_lidas=linhas_lidas,
        rotulos=dict(contagem),
    )
