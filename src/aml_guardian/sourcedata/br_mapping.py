"""Loader de `data/mappings/saml_d_to_br.yaml`: rótulos do SAML-D → domínio do DT-02 (T0.7, SPEC.md §8.3).

Como no mapeamento de tipologias da T0.6, a correspondência é dado versionado e nunca conversão implícita em
código: nenhuma regra geral leva `Cash Deposit` a `ESPECIE_DEPOSITO` ou `UK` a `BR`.

O arquivo MUST cobrir exatamente os valores que a base de origem contém — o loader falha se sobrar ou faltar
rótulo, porque um `Payment_type` sem correspondência viraria transação descartada em silêncio.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Self

from pydantic import Field, StringConstraints, model_validator

from aml_guardian.config._base import Aprovacao, _ConfigModel, load_config
from aml_guardian.contracts.ingestion import NonEmptyStr, PaymentType
from aml_guardian.contracts.pipeline import VersionNumber
from aml_guardian.sourcedata.mapping import MAPPINGS_DIR

SAML_D_BR_FILE = "saml_d_to_br.yaml"

#: Sigla do país doméstico da instituição da PoC.
PAIS_DOMESTICO = "BR"

#: Os 7 valores da coluna `Payment_type`, conferidos no SAML-D real (9.504.852 linhas).
PAYMENT_TYPES_SAML_D = frozenset(
    ["Cash Deposit", "Cash Withdrawal", "Cross-border", "Debit card", "Credit card", "ACH", "Cheque"]
)

#: Os 18 países de `Sender_bank_location`/`Receiver_bank_location`, conferidos no SAML-D real.
PAISES_SAML_D = frozenset(
    [
        "UK",
        "Germany",
        "France",
        "Italy",
        "Spain",
        "Netherlands",
        "Austria",
        "Switzerland",
        "Turkey",
        "Albania",
        "USA",
        "Mexico",
        "Japan",
        "India",
        "Pakistan",
        "UAE",
        "Morocco",
        "Nigeria",
    ]
)

Pais = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]


class BrMappingError(ValueError):
    """Rótulo do SAML-D sem correspondência no mapeamento versionado."""


def _divergencia(presentes: set[str], esperados: frozenset[str], campo: str) -> str | None:
    faltando = sorted(esperados - presentes)
    sobrando = sorted(presentes - esperados)
    if not faltando and not sobrando:
        return None
    partes = []
    if faltando:
        partes.append(f"sem rótulo do SAML-D para {faltando}")
    if sobrando:
        partes.append(f"rótulo(s) fora do SAML-D: {sobrando}")
    return f"{campo}: {'; '.join(partes)}"


class BrMapping(_ConfigModel):
    """Conteúdo de `saml_d_to_br.yaml`; `br_mapping_version` é gravado no `core_sintetico` como proveniência."""

    br_mapping_version: VersionNumber
    aprovacao: Aprovacao
    payment_types: Annotated[dict[NonEmptyStr, PaymentType], Field(min_length=1)]
    paises: Annotated[dict[NonEmptyStr, Pais], Field(min_length=1)]

    @model_validator(mode="after")
    def _cobertura_dos_payment_types(self) -> Self:
        divergencia = _divergencia(set(self.payment_types), PAYMENT_TYPES_SAML_D, "payment_types")
        if divergencia:
            raise ValueError(divergencia)
        faltando = set(PaymentType) - set(self.payment_types.values())
        if faltando:
            raise ValueError(f"payment_types: nenhum rótulo do SAML-D mapeia {sorted(item.value for item in faltando)}")
        return self

    @model_validator(mode="after")
    def _cobertura_dos_paises(self) -> Self:
        divergencia = _divergencia(set(self.paises), PAISES_SAML_D, "paises")
        if divergencia:
            raise ValueError(divergencia)
        domesticos = sorted(rotulo for rotulo, sigla in self.paises.items() if sigla == PAIS_DOMESTICO)
        if len(domesticos) != 1:
            raise ValueError(
                f"paises: exatamente um país do SAML-D deve mapear {PAIS_DOMESTICO}; encontrados {domesticos}"
            )
        siglas = list(self.paises.values())
        if len(set(siglas)) != len(siglas):
            repetidas = sorted({sigla for sigla in siglas if siglas.count(sigla) > 1})
            raise ValueError(f"paises: mesma sigla para mais de um país do SAML-D: {repetidas}")
        return self

    @property
    def pais_domestico(self) -> str:
        """Rótulo do SAML-D que a camada brasileira trata como Brasil (decisão da T0.7: `UK`)."""
        return next(rotulo for rotulo, sigla in self.paises.items() if sigla == PAIS_DOMESTICO)

    def payment_type(self, rotulo: str) -> PaymentType:
        """Valor do DT-02 para um `Payment_type` do SAML-D."""
        try:
            return self.payment_types[rotulo]
        except KeyError:
            raise BrMappingError(f"Payment_type {rotulo!r} ausente de {SAML_D_BR_FILE}") from None

    def pais(self, rotulo: str) -> str:
        """Sigla de duas letras para uma localização bancária do SAML-D."""
        try:
            return self.paises[rotulo]
        except KeyError:
            raise BrMappingError(f"localização bancária {rotulo!r} ausente de {SAML_D_BR_FILE}") from None


def load_br_mapping(path: Path | None = None) -> BrMapping:
    """Carrega o mapeamento da camada brasileira; sem `path`, usa o arquivo versionado em `data/mappings/`."""
    return load_config(path or MAPPINGS_DIR / SAML_D_BR_FILE, BrMapping)
