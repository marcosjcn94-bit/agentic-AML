"""Base comum dos loaders de configuração versionada em `config/` (T0.5).

Todo YAML é lido com `yaml.safe_load` e validado por modelo Pydantic estrito: chave desconhecida, chave ausente ou
tipo errado falham com `ConfigError` citando o arquivo, nunca com valor padrão silencioso.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Annotated, TypeVar

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from aml_guardian.contracts.ingestion import NonEmptyStr

CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"

ModelT = TypeVar("ModelT", bound=BaseModel)


class ConfigError(ValueError):
    """Arquivo de configuração ausente, malformado ou fora do schema."""


class _ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Situacao(StrEnum):
    """Situação do aceite do autor sobre os valores de uma seção (`TASKS.md` §1, Ask First)."""

    PROVISORIO = "provisorio"
    DEFINITIVO = "definitivo"


class Aprovacao(_ConfigModel):
    """Registro do aceite dos valores no próprio arquivo: quem, quando, situação e origem da decisão."""

    por: NonEmptyStr
    em: Annotated[date, Field(strict=True)]
    situacao: Situacao
    referencia: NonEmptyStr


def load_config(path: Path, model: type[ModelT]) -> ModelT:
    """Lê `path` como YAML e valida contra `model`, convertendo toda falha em `ConfigError`."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"{path.name}: não foi possível ler o arquivo ({exc})") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path.name}: YAML inválido ({exc})") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{path.name}: o documento deve ser um mapeamento YAML")
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"{path.name}: {exc}") from exc
