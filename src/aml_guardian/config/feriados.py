"""Loader de `config/feriados.yaml`: calendário de dias não úteis usado no controle de prazo (RF-09).

Cada data cita a fonte oficial declarada no próprio arquivo. O calendário cobre um período fechado de anos;
o cálculo de `prazo_comunicacao` (próximo dia útil) fica no módulo de prazos e deve recusar data fora do período.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated, Self

from pydantic import Field, HttpUrl, StrictInt, StringConstraints, model_validator

from aml_guardian.config._base import CONFIG_DIR, Aprovacao, _ConfigModel, load_config
from aml_guardian.contracts.ingestion import NonEmptyStr

FERIADOS_FILE = "feriados.yaml"

FonteId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_]+$")]
Ano = Annotated[StrictInt, Field(ge=1900, le=2100)]


class Fonte(_ConfigModel):
    id: FonteId
    referencia: NonEmptyStr
    url: HttpUrl


class Feriado(_ConfigModel):
    data: Annotated[date, Field(strict=True)]
    nome: NonEmptyStr
    fonte: FonteId


class Periodo(_ConfigModel):
    ano_inicio: Ano
    ano_fim: Ano

    @model_validator(mode="after")
    def _ordem(self) -> Self:
        if self.ano_inicio > self.ano_fim:
            raise ValueError("ano_inicio posterior a ano_fim")
        return self

    def contem(self, dia: date) -> bool:
        return self.ano_inicio <= dia.year <= self.ano_fim


class FeriadosConfig(_ConfigModel):
    """Conteúdo de `feriados.yaml`; datas em ordem crescente, únicas, dentro do período e com fonte declarada."""

    periodo: Periodo
    aprovacao: Aprovacao
    fontes: Annotated[list[Fonte], Field(min_length=1)]
    feriados: Annotated[list[Feriado], Field(min_length=1)]

    @model_validator(mode="after")
    def _coerencia(self) -> Self:
        fonte_ids = [fonte.id for fonte in self.fontes]
        if len(set(fonte_ids)) != len(fonte_ids):
            raise ValueError("id de fonte repetido")
        anterior: date | None = None
        for feriado in self.feriados:
            if feriado.fonte not in fonte_ids:
                raise ValueError(f"{feriado.data}: fonte {feriado.fonte!r} não declarada em fontes")
            if not self.periodo.contem(feriado.data):
                raise ValueError(f"{feriado.data}: fora do período {self.periodo.ano_inicio}-{self.periodo.ano_fim}")
            if anterior is not None and feriado.data <= anterior:
                raise ValueError(f"{feriado.data}: datas devem ser únicas e em ordem crescente")
            anterior = feriado.data
        return self

    @property
    def datas(self) -> frozenset[date]:
        return frozenset(feriado.data for feriado in self.feriados)

    def is_feriado(self, dia: date) -> bool:
        """`True` se `dia` é feriado; `ValueError` se estiver fora do período coberto (evita dia útil falso)."""
        if not self.periodo.contem(dia):
            raise ValueError(f"{dia}: fora do período coberto por {FERIADOS_FILE}")
        return dia in self.datas


def load_feriados(path: Path | None = None) -> FeriadosConfig:
    """Carrega o calendário; sem `path`, usa o arquivo versionado em `config/`."""
    return load_config(path or CONFIG_DIR / FERIADOS_FILE, FeriadosConfig)
