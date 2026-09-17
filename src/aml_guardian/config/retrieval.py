"""Loader de `config/retrieval.yaml`: limiar de descarte da Seleção determinística (RF-06, T1.8 Ask First)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import Field

from aml_guardian.config._base import CONFIG_DIR, Aprovacao, _ConfigModel, load_config

RETRIEVAL_FILE = "retrieval.yaml"

Score = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]


class SelectionConfig(_ConfigModel):
    """`selection.min_score`: trechos abaixo deste score são descartados na Seleção (RF-06)."""

    min_score: Score


class RetrievalConfig(_ConfigModel):
    """Conteúdo de `retrieval.yaml`."""

    selection: SelectionConfig
    aprovacao: Aprovacao


def load_retrieval(path: Path | None = None) -> RetrievalConfig:
    """Carrega a configuração de recuperação; sem `path`, usa o arquivo versionado em `config/`."""
    return load_config(path or CONFIG_DIR / RETRIEVAL_FILE, RetrievalConfig)
