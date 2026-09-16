"""Loader de `data/mappings/saml_d_to_cc4001.yaml`: tipologias do SAML-D → Carta Circular BCB 4.001/2020 (SPEC.md §3.2).

O arquivo é chaveado pelo rótulo exato do SAML-D (`Layered_Fan_In`), que difere da grafia de exibição do enum
`Typology` (`Layered Fan-In`): a correspondência é dado versionado, nunca conversão implícita em código.
`article_ref` e `applicability` alimentam a seleção determinística de trechos (RF-06, ADR-013) e ficam vazios
até T1.8/M4 — vazio é explícito no arquivo (`[]` e `null`), nunca chave omitida.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Self

from pydantic import Field, HttpUrl, StrictBool, StringConstraints, model_validator

from aml_guardian.config._base import Aprovacao, _ConfigModel, load_config
from aml_guardian.contracts.ingestion import NonEmptyStr
from aml_guardian.contracts.pipeline import Applicability, Inciso, Typology, VersionNumber

MAPPINGS_DIR = Path(__file__).resolve().parents[3] / "data" / "mappings"
SAML_D_MAPPING_FILE = "saml_d_to_cc4001.yaml"

#: Tipologias marcadas como críticas na tabela do SPEC.md §3.2.
CRITICAS_ESPERADAS = 6

#: Incisos que o art. 1º da CC 4.001/2020 de fato contém (I a XVII), conferidos no texto oficial publicado pelo BCB
#: (`exibenormativo?p1=Carta%20Circular&p2=4001`). O tipo `Inciso` só garante algarismo romano bem formado: sem esta
#: lista, um enquadramento em inciso inexistente na norma entraria no dossiê (RF-14, factualidade).
INCISOS_CC4001_ART1 = frozenset(
    ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII"]
)

#: Rótulo como aparece na coluna de tipologia do CSV: `Stacked Bipartite` tem espaço; os demais, `_` ou `-`.
SamlLabel = Annotated[str, StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9_ -]*$")]
Alinea = Annotated[str, StringConstraints(pattern=r"^[a-z]$")]


class Fonte(_ConfigModel):
    """Norma de enquadramento citada pelo mapeamento."""

    referencia: NonEmptyStr
    url: HttpUrl


class Tipologia(_ConfigModel):
    """Enquadramento de um rótulo suspeito do SAML-D no art. 1º da CC 4.001/2020 (SPEC.md §3.2)."""

    typology: Typology
    incisos: Annotated[list[Inciso], Field(min_length=1)]
    alineas: list[Alinea]
    critica: StrictBool
    article_ref: list[NonEmptyStr]
    applicability: Applicability | None

    @model_validator(mode="after")
    def _sem_repeticao(self) -> Self:
        for campo in ("incisos", "alineas", "article_ref"):
            valores: list[str] = getattr(self, campo)
            if len(set(valores)) != len(valores):
                raise ValueError(f"{campo}: valores repetidos")
        if self.typology is Typology.NENHUMA:
            raise ValueError("typology: NENHUMA não é rótulo do SAML-D")
        fora = [inciso for inciso in self.incisos if inciso not in INCISOS_CC4001_ART1]
        if fora:
            raise ValueError(f"incisos: {fora} não existem no art. 1º da CC 4.001/2020 (I a XVII)")
        return self


class SamlDMapping(_ConfigModel):
    """Conteúdo de `saml_d_to_cc4001.yaml`; `mapping_version` é gravado em cada dossiê (SPEC.md §3.2)."""

    mapping_version: VersionNumber
    fonte: Fonte
    aprovacao: Aprovacao
    tipologias: Annotated[dict[SamlLabel, Tipologia], Field(min_length=1)]
    normais: Annotated[list[SamlLabel], Field(min_length=1)]

    @model_validator(mode="after")
    def _cobertura(self) -> Self:
        tipologias = [item.typology for item in self.tipologias.values()]
        if len(set(tipologias)) != len(tipologias):
            raise ValueError("tipologias: mesma Typology mapeada por mais de um rótulo do SAML-D")
        faltando = {opcao for opcao in Typology if opcao is not Typology.NENHUMA} - set(tipologias)
        if faltando:
            raise ValueError(f"tipologias: sem rótulo do SAML-D para {sorted(opcao.value for opcao in faltando)}")
        criticas = sum(1 for item in self.tipologias.values() if item.critica)
        if criticas != CRITICAS_ESPERADAS:
            raise ValueError(f"tipologias: {criticas} críticas; a tabela do SPEC.md §3.2 define {CRITICAS_ESPERADAS}")
        if len(set(self.normais)) != len(self.normais):
            raise ValueError("normais: rótulos repetidos")
        repetidos = set(self.normais) & set(self.tipologias)
        if repetidos:
            raise ValueError(f"normais: rótulos também listados em tipologias: {sorted(repetidos)}")
        return self

    @property
    def rotulos(self) -> frozenset[str]:
        """Todos os rótulos aceitos na coluna de tipologia do SAML-D: 17 suspeitos e os normais."""
        return frozenset(self.tipologias) | frozenset(self.normais)

    def is_suspeito(self, rotulo: str) -> bool:
        """`True` se o rótulo tem enquadramento na CC 4.001/2020; `False` para os rótulos normais."""
        return rotulo in self.tipologias


def load_saml_d_mapping(path: Path | None = None) -> SamlDMapping:
    """Carrega o mapeamento; sem `path`, usa o arquivo versionado em `data/mappings/`."""
    return load_config(path or MAPPINGS_DIR / SAML_D_MAPPING_FILE, SamlDMapping)
