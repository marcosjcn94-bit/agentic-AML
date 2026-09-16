"""Loader de `config/cambio.yaml`: taxas de câmbio sintéticas da camada brasileira (T0.7, SPEC.md §8.3).

As taxas NÃO são cotações reais: são valores fixos, versionados e aprovados no próprio arquivo, escolhidos para
que a base sintética tenha ordem de grandeza compatível com os limiares em BRL do `triage_rules.yaml`.
Toda aritmética é `Decimal`: `float` é recusado na entrada e na configuração para não herdar imprecisão binária,
como já exige o `amount_brl` do DT-02.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Annotated, Self

from pydantic import BeforeValidator, Field, model_validator

from aml_guardian.config._base import CONFIG_DIR, Aprovacao, _ConfigModel, load_config
from aml_guardian.contracts.ingestion import CurrencyCode, NonEmptyStr
from aml_guardian.contracts.pipeline import VersionNumber

CAMBIO_FILE = "cambio.yaml"

#: Casas decimais do `amount_brl` do DT-02.
CENTAVO = Decimal("0.01")


class CambioError(ValueError):
    """Moeda fora da tabela versionada, valor não numérico ou conversão que não resulta em valor positivo."""


def _recusa_inexato(value: object) -> object:
    """Recusa `float` e `bool` antes da conversão para que a taxa não nasça de um binário impreciso."""
    if isinstance(value, bool | float):
        raise ValueError("taxa_brl deve ser decimal exato (string, int ou Decimal)")
    return value


TaxaBRL = Annotated[Decimal, BeforeValidator(_recusa_inexato), Field(gt=0, allow_inf_nan=False)]


class Moeda(_ConfigModel):
    """Uma moeda do SAML-D: código ISO-4217 do DT-02 e quanto vale, em BRL, uma unidade dela."""

    iso: CurrencyCode
    taxa_brl: TaxaBRL


class CambioConfig(_ConfigModel):
    """Conteúdo de `cambio.yaml`; `cambio_version` é gravado no `core_sintetico` como proveniência."""

    cambio_version: VersionNumber
    aprovacao: Aprovacao
    moedas: Annotated[dict[NonEmptyStr, Moeda], Field(min_length=1)]

    @model_validator(mode="after")
    def _iso_sem_repeticao(self) -> Self:
        codigos = [moeda.iso for moeda in self.moedas.values()]
        if len(set(codigos)) != len(codigos):
            repetidos = sorted({codigo for codigo in codigos if codigos.count(codigo) > 1})
            raise ValueError(f"moedas: mesmo código ISO para mais de um rótulo do SAML-D: {repetidos}")
        return self

    def _moeda(self, rotulo: str) -> Moeda:
        try:
            return self.moedas[rotulo]
        except KeyError:
            raise CambioError(
                f"moeda {rotulo!r} ausente de {CAMBIO_FILE} (cambio_version {self.cambio_version})"
            ) from None

    def iso(self, rotulo: str) -> str:
        """Código ISO-4217 da moeda, para `currency_sent`/`currency_received` do DT-02."""
        return self._moeda(rotulo).iso

    def converte(self, valor: str | int | Decimal, rotulo: str) -> Decimal:
        """Converte `valor` na moeda `rotulo` para BRL, arredondado a 2 casas (ROUND_HALF_UP).

        Falha se o resultado não for positivo: o `amount_brl` do DT-02 exige valor > 0, e um valor que some no
        arredondamento seria uma transação inexistente entrando na base.
        """
        if isinstance(valor, bool | float):
            raise CambioError(f"valor a converter deve ser decimal exato, não {type(valor).__name__}")
        try:
            origem = Decimal(str(valor))
        except InvalidOperation:
            raise CambioError(f"valor a converter não é numérico: {valor!r}") from None
        convertido = (origem * self._moeda(rotulo).taxa_brl).quantize(CENTAVO, rounding=ROUND_HALF_UP)
        if convertido <= 0:
            raise CambioError(f"{valor!r} em {rotulo!r} arredonda para {convertido}; o DT-02 exige amount_brl > 0")
        return convertido


def load_cambio(path: Path | None = None) -> CambioConfig:
    """Carrega as taxas de câmbio; sem `path`, usa o arquivo versionado em `config/`."""
    return load_config(path or CONFIG_DIR / CAMBIO_FILE, CambioConfig)
