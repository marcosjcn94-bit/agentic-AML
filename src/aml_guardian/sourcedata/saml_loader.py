"""Loader do CSV do SAML-D: valida colunas e rótulos de tipologia contra o mapeamento (SPEC.md §8.3, ADR-005).

O arquivo real tem ~9,5 milhões de linhas e não é versionado (CC BY-NC-SA 4.0, fica em `data/raw/`): a leitura é
sempre por streaming com `csv.reader`, sem carregar a base em memória e sem dependência de dataframe.
Toda divergência falha com mensagem explícita citando a coluna, o rótulo e a linha — nunca com descarte silencioso.
"""

from __future__ import annotations

import csv
from collections import Counter
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from aml_guardian.sourcedata.mapping import SAML_D_MAPPING_FILE, SamlDMapping, load_saml_d_mapping

RAW_DIR = Path(__file__).resolve().parents[3] / "data" / "raw"
SAML_D_FILE = "SAML-D.csv"

#: Colunas de nome único esperadas pelo artigo de origem (SPEC.md §8.3).
FIXED_COLUMNS = (
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
)
#: Colunas que o artigo de origem publica com dois nomes alternativos (SPEC.md §8.3).
FLAG_COLUMNS = ("Is_laundering", "Is_Suspicious")
TYPE_COLUMNS = ("Laundering_type", "Type")

_FLAG_VALUES = {"0": False, "1": True}


class SamlLoaderError(ValueError):
    """CSV do SAML-D ausente, com coluna divergente, rótulo fora do mapeamento ou linha incoerente."""


@dataclass(frozen=True)
class SamlHeader:
    """Cabeçalho aceito, com o nome efetivo das duas colunas de nome alternativo."""

    columns: tuple[str, ...]
    flag_column: str
    type_column: str

    def index(self, column: str) -> int:
        return self.columns.index(column)


@dataclass(frozen=True)
class LoadReport:
    """Resumo de uma passada completa pelo arquivo, usado como evidência de execução sobre o SAML-D real."""

    linhas: int
    por_rotulo: dict[str, int]
    suspeitas: int
    normais: int


def _resolve(colunas: tuple[str, ...], alternativas: tuple[str, ...], problemas: list[str]) -> str:
    presentes = [nome for nome in alternativas if nome in colunas]
    if not presentes:
        problemas.append(f"nenhuma das colunas {list(alternativas)} está no cabeçalho")
        return ""
    if len(presentes) > 1:
        problemas.append(f"colunas alternativas ambíguas no mesmo cabeçalho: {presentes}")
    return presentes[0]


def validate_header(header: Sequence[str], path: Path) -> SamlHeader:
    """Valida o cabeçalho contra o SPEC.md §8.3 e resolve as colunas de nome alternativo."""
    colunas = tuple(nome.strip() for nome in header)
    problemas: list[str] = []
    faltando = [nome for nome in FIXED_COLUMNS if nome not in colunas]
    if faltando:
        problemas.append(f"coluna(s) ausente(s): {faltando}")
    flag_column = _resolve(colunas, FLAG_COLUMNS, problemas)
    type_column = _resolve(colunas, TYPE_COLUMNS, problemas)
    conhecidas = {*FIXED_COLUMNS, *FLAG_COLUMNS, *TYPE_COLUMNS}
    extras = [nome for nome in colunas if nome not in conhecidas]
    if extras:
        problemas.append(f"coluna(s) não prevista(s): {extras}")
    if len(set(colunas)) != len(colunas):
        problemas.append("coluna(s) repetida(s) no cabeçalho")
    if problemas:
        raise SamlLoaderError(f"{path.name}: {'; '.join(problemas)}")
    return SamlHeader(colunas, flag_column, type_column)


@contextmanager
def _abre(path: Path) -> Iterator[TextIO]:
    try:
        handle = path.open(newline="", encoding="utf-8-sig")
    except OSError as exc:
        raise SamlLoaderError(f"{path}: não foi possível ler o CSV do SAML-D ({exc})") from exc
    try:
        yield handle
    finally:
        handle.close()


def read_header(path: Path | None = None) -> SamlHeader:
    """Lê e valida apenas o cabeçalho do arquivo."""
    alvo = path or RAW_DIR / SAML_D_FILE
    with _abre(alvo) as handle:
        primeira = next(csv.reader(handle), None)
        if primeira is None:
            raise SamlLoaderError(f"{alvo.name}: arquivo vazio, sem cabeçalho")
        return validate_header(primeira, alvo)


def iter_transactions(
    path: Path | None = None,
    mapping: SamlDMapping | None = None,
    header: SamlHeader | None = None,
) -> Iterator[dict[str, str]]:
    """Percorre o CSV validando cada linha contra o mapeamento e devolve as células por nome de coluna.

    `header` reaproveita um cabeçalho já validado pelo chamador sobre este mesmo arquivo (`read_header`), para não
    validar a primeira linha duas vezes na mesma passada; sem ele, o cabeçalho é lido e validado aqui.
    """
    alvo = path or RAW_DIR / SAML_D_FILE
    mapa = mapping or load_saml_d_mapping()
    with _abre(alvo) as handle:
        leitor = csv.reader(handle)
        primeira = next(leitor, None)
        if primeira is None:
            raise SamlLoaderError(f"{alvo.name}: arquivo vazio, sem cabeçalho")
        cabecalho = header or validate_header(primeira, alvo)
        indice_tipo = cabecalho.index(cabecalho.type_column)
        indice_flag = cabecalho.index(cabecalho.flag_column)
        for numero, linha in enumerate(leitor, start=2):
            if len(linha) != len(cabecalho.columns):
                raise SamlLoaderError(
                    f"{alvo.name}:{numero}: {len(linha)} células para {len(cabecalho.columns)} colunas"
                )
            rotulo = linha[indice_tipo]
            if rotulo not in mapa.rotulos:
                raise SamlLoaderError(
                    f"{alvo.name}:{numero}: rótulo de tipologia {rotulo!r} ausente de {SAML_D_MAPPING_FILE}"
                )
            bruto = linha[indice_flag]
            if bruto not in _FLAG_VALUES:
                raise SamlLoaderError(f"{alvo.name}:{numero}: {cabecalho.flag_column} = {bruto!r}; esperado '0' ou '1'")
            if _FLAG_VALUES[bruto] is not mapa.is_suspeito(rotulo):
                raise SamlLoaderError(
                    f"{alvo.name}:{numero}: {cabecalho.flag_column} = {bruto!r} incoerente com o rótulo {rotulo!r}"
                )
            yield dict(zip(cabecalho.columns, linha, strict=True))


def validate_file(path: Path | None = None, mapping: SamlDMapping | None = None) -> LoadReport:
    """Percorre o arquivo inteiro e resume a contagem por rótulo; levanta na primeira divergência."""
    alvo = path or RAW_DIR / SAML_D_FILE
    mapa = mapping or load_saml_d_mapping()
    cabecalho = read_header(alvo)
    contagem: Counter[str] = Counter()
    for linha in iter_transactions(alvo, mapa, cabecalho):
        contagem[linha[cabecalho.type_column]] += 1
    suspeitas = sum(total for rotulo, total in contagem.items() if mapa.is_suspeito(rotulo))
    return LoadReport(
        linhas=sum(contagem.values()),
        por_rotulo=dict(contagem),
        suspeitas=suspeitas,
        normais=sum(contagem.values()) - suspeitas,
    )
