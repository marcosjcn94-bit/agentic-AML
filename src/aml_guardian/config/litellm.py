"""Loader de `config/litellm.yaml`: roteamento de modelo, cache semântico e seleção de trechos.

O nome do provedor e do modelo existe só no YAML (ADR-010, RNF-10): o código referencia apenas o alias.
`model_list` segue o formato do LiteLLM Router. Parâmetros de geração seguem o ADR-013 e o RNF-09
(`temperature` 0 e `seed` fixo) e o teto de saída do RF-05.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Self

from pydantic import Field, HttpUrl, StrictBool, StrictInt, StringConstraints, model_validator

from aml_guardian.config._base import CONFIG_DIR, Aprovacao, _ConfigModel, load_config
from aml_guardian.contracts.ingestion import NonEmptyStr

LITELLM_FILE = "litellm.yaml"
MAX_OUTPUT_TOKENS = 60

PositiveInt = Annotated[StrictInt, Field(ge=1)]
ModelRef = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_]+/\S+$")]
Score = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]


class LiteLLMParams(_ConfigModel):
    """Parâmetros repassados ao LiteLLM para o alias (ADR-013, relatório de benchmark v2)."""

    model: ModelRef
    api_base: HttpUrl
    temperature: Annotated[float, Field(strict=True, ge=0, le=0)]
    seed: StrictInt
    num_ctx: PositiveInt
    num_predict: Annotated[StrictInt, Field(ge=1, le=MAX_OUTPUT_TOKENS)]
    num_thread: PositiveInt


class ModelEntry(_ConfigModel):
    model_name: NonEmptyStr
    litellm_params: LiteLLMParams


class InvestigationRouting(_ConfigModel):
    """Alias usado pelo nó de Investigação, o único nó LLM (ADR-013)."""

    model_alias: NonEmptyStr
    aprovacao: Aprovacao


class CacheConfig(_ConfigModel):
    """Cache semântico normativo (RF-04): acerto se cosseno ≥ `threshold`; desligável para as medições."""

    enabled: StrictBool
    threshold: Annotated[float, Field(strict=True, gt=0, le=1, allow_inf_nan=False)]
    aprovacao: Aprovacao


class SelectionConfig(_ConfigModel):
    """Seleção determinística de trechos (RF-06): descarta candidato com cosseno < `min_score`."""

    min_score: Score
    aprovacao: Aprovacao


class LiteLLMConfig(_ConfigModel):
    """Conteúdo de `litellm.yaml`."""

    model_list: Annotated[list[ModelEntry], Field(min_length=1)]
    investigation: InvestigationRouting
    cache: CacheConfig
    selection: SelectionConfig

    @model_validator(mode="after")
    def _alias_resolvido(self) -> Self:
        names = [entry.model_name for entry in self.model_list]
        if len(set(names)) != len(names):
            raise ValueError("model_name repetido em model_list")
        if self.investigation.model_alias not in names:
            raise ValueError(f"alias {self.investigation.model_alias!r} ausente de model_list")
        return self

    def params_for(self, alias: str) -> LiteLLMParams:
        """Parâmetros do alias; `KeyError` se não existir."""
        for entry in self.model_list:
            if entry.model_name == alias:
                return entry.litellm_params
        raise KeyError(alias)


def load_litellm(path: Path | None = None) -> LiteLLMConfig:
    """Carrega a configuração do gateway; sem `path`, usa o arquivo versionado em `config/`."""
    return load_config(path or CONFIG_DIR / LITELLM_FILE, LiteLLMConfig)
