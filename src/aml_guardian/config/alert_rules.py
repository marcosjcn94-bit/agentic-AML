"""Loader de `config/alert_rules.yaml`: regras do gerador de alertas legado simulado (T0.8, SPEC.md §8.3).

Regras clássicas e ingênuas de monitoramento legado — não são os detectores críticos de `triage_rules.yaml`
(RF-03). Servem de entrada ruidosa (falso positivo alto) para a triagem determinística avaliar depois.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import Field, StrictInt

from aml_guardian.config._base import CONFIG_DIR, Aprovacao, _ConfigModel, load_config
from aml_guardian.contracts.ingestion import AmountBRL, NonEmptyStr
from aml_guardian.contracts.pipeline import VersionNumber

ALERT_RULES_FILE = "alert_rules.yaml"

JanelaDias = Annotated[StrictInt, Field(ge=1)]


class ValorElevado(_ConfigModel):
    """Regra A: transação isolada com `amount_brl >= limiar_brl` dispara alerta."""

    descricao: NonEmptyStr
    limiar_brl: AmountBRL
    janela_agrupamento_dias: JanelaDias


class ContagemVelocidade(_ConfigModel):
    """Regra B: `min_transacoes` ou mais transações da mesma conta remetente em janela móvel."""

    descricao: NonEmptyStr
    min_transacoes: Annotated[StrictInt, Field(ge=2)]
    janela_dias: JanelaDias


class RegrasLegado(_ConfigModel):
    valor_elevado: ValorElevado
    contagem_velocidade: ContagemVelocidade


class AlertRulesConfig(_ConfigModel):
    """Conteúdo de `alert_rules.yaml`; `alert_rules_version` alimenta `source_rule_id` e a auditoria."""

    alert_rules_version: VersionNumber
    aprovacao: Aprovacao
    regras: RegrasLegado


def load_alert_rules(path: Path | None = None) -> AlertRulesConfig:
    """Carrega as regras do gerador de alertas legado; sem `path`, usa o arquivo versionado em `config/`."""
    return load_config(path or CONFIG_DIR / ALERT_RULES_FILE, AlertRulesConfig)
