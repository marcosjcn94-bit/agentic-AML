"""Loader de `config/baseline.yaml`: premissas do processo manual simulado (SPEC.md §3.3, §10, §12).

`velocidade = tempo_manual_min / (latência_média_min + tempo_revisao_min)`; os dois parâmetros são gravados no
relatório de avaliação.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Self

from pydantic import Field, model_validator

from aml_guardian.config._base import CONFIG_DIR, Aprovacao, _ConfigModel, load_config

BASELINE_FILE = "baseline.yaml"

Minutes = Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False)]


class BaselineConfig(_ConfigModel):
    """Conteúdo de `baseline.yaml`."""

    tempo_manual_min: Minutes
    tempo_revisao_min: Minutes
    aprovacao: Aprovacao

    @model_validator(mode="after")
    def _revisao_menor_que_manual(self) -> Self:
        if self.tempo_revisao_min >= self.tempo_manual_min:
            raise ValueError("tempo_revisao_min deve ser menor que tempo_manual_min")
        return self


def load_baseline(path: Path | None = None) -> BaselineConfig:
    """Carrega o baseline; sem `path`, usa o arquivo versionado em `config/`."""
    return load_config(path or CONFIG_DIR / BASELINE_FILE, BaselineConfig)
