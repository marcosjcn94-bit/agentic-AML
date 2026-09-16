"""Loader de `config/triage_rules.yaml`: regras versionadas da triagem determinística (RF-03, RNF-09).

Os quatro detectores críticos do RF-03 são obrigatórios e marcados `critico: true`; nenhum pode ser desligado por
configuração, porque a triagem MUST executá-los antes de qualquer proposta de arquivamento.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, StrictBool, StrictInt, model_validator

from aml_guardian.config._base import CONFIG_DIR, Aprovacao, _ConfigModel, load_config
from aml_guardian.contracts.ingestion import AmountBRL, NonEmptyStr
from aml_guardian.contracts.pipeline import VersionNumber

TRIAGE_RULES_FILE = "triage_rules.yaml"

JanelaDias = Annotated[StrictInt, Field(ge=1)]
ListaRestricao = Literal["pep", "ceis", "cnep"]


class _Detector(_ConfigModel):
    descricao: NonEmptyStr
    critico: StrictBool

    @model_validator(mode="after")
    def _sempre_critico(self) -> Self:
        if not self.critico:
            raise ValueError("critico: detector do RF-03 não pode ser desligado")
        return self


class Fragmentacao(_Detector):
    """N transações abaixo de limiar em janela (RF-03; também alimenta F03 do DT-16)."""

    limiar_brl: AmountBRL
    min_transacoes: Annotated[StrictInt, Field(ge=2)]
    janela_dias: JanelaDias


class Camadas(_Detector):
    """Dispersão/concentração em camadas: fan-in/fan-out com profundidade ≥ 2 (RF-03; alimenta F08)."""

    profundidade_minima: Annotated[StrictInt, Field(ge=2)]
    min_contrapartes: Annotated[StrictInt, Field(ge=2)]
    janela_dias: JanelaDias


class EspecieDepoisExterior(_Detector):
    """Depósito em espécie seguido de envio transfronteiriço (RF-03; alimenta F10)."""

    janela_dias: JanelaDias


class ListaRestricaoDetector(_Detector):
    """Acerto em lista de restrição consultada via MCP-02 (RF-03; alimenta F13)."""

    listas: Annotated[list[ListaRestricao], Field(min_length=1)]

    @model_validator(mode="after")
    def _listas_unicas(self) -> Self:
        if len(set(self.listas)) != len(self.listas):
            raise ValueError("listas de restrição repetidas")
        return self


class DetectoresCriticos(_ConfigModel):
    fragmentacao: Fragmentacao
    camadas: Camadas
    especie_depois_exterior: EspecieDepoisExterior
    lista_restricao: ListaRestricaoDetector


class TriageRulesConfig(_ConfigModel):
    """Conteúdo de `triage_rules.yaml`; `rules_version` vai para DT-06, DT-11 e DT-12."""

    rules_version: VersionNumber
    aprovacao: Aprovacao
    detectores_criticos: DetectoresCriticos


def load_triage_rules(path: Path | None = None) -> TriageRulesConfig:
    """Carrega as regras de triagem; sem `path`, usa o arquivo versionado em `config/`."""
    return load_config(path or CONFIG_DIR / TRIAGE_RULES_FILE, TriageRulesConfig)
