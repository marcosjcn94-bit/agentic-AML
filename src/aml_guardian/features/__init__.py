"""Pré-passo de indicadores (T1.5, DT-16, `features_version = 1`, AGENTS.md §4.3)."""

from aml_guardian.features.catalog import FEATURES_VERSION, calcular_indicadores

__all__ = ["FEATURES_VERSION", "calcular_indicadores"]
