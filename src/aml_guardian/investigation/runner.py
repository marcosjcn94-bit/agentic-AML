"""Orquestração do nó Investigação (T1.6, RF-05, AGENTS.md §2.3): pré-passo + chamada LLM + pós-processamento.

Só roda para `TriageLevel.INVESTIGAR` (AGENTS.md §1). MCP indisponível no pré-passo, estouro do teto de 300
tokens mesmo sem F14+, JSON inválido após os retries, e "detector crítico ou tipologia crítica com ARQUIVAR"
levam a `NEEDS_HUMAN` (RF-05, RF-10), preservando o que já foi calculado (AGENTS.md §2.8).
"""

from __future__ import annotations

import hashlib
from typing import Self
from uuid import UUID

from pydantic import model_validator

from aml_guardian.audit.chain import add_event
from aml_guardian.config.litellm import LiteLLMConfig
from aml_guardian.config.triage import TriageRulesConfig
from aml_guardian.contracts.ingestion import AlertState, NonEmptyStr, SanitizedAlert, TriageLevel, _Contract
from aml_guardian.contracts.pipeline import (
    InvestigationFeatures,
    InvestigationOutput,
    Recommendation,
    TriageDecision,
    missing_evidence_ids,
)
from aml_guardian.contracts.runtime import Role
from aml_guardian.features import calcular_indicadores
from aml_guardian.features.catalog import HistoryFetcher
from aml_guardian.investigation.contract import PROMPT_VERSION, schema_geracao, validar_saida
from aml_guardian.investigation.litellm_client import ContadorChamadas, RespostaModelo, chamar_modelo, resolver_params
from aml_guardian.investigation.prompt_builder import montar_prompt
from aml_guardian.mcp_servers.server import check_restriction_lists, get_customer_history
from aml_guardian.sourcedata.mapping import SamlDMapping, load_saml_d_mapping
from aml_guardian.triage.engine import MCPIndisponivelError, RestrictionChecker

MAX_RETRIES = 2  # AGENTS.md §1: no máximo 2 retries com backoff (backoff não é medido nesta PoC, ver relatório)


class InvestigationResult(_Contract):
    """Resultado do nó Investigação: `INVESTIGATING` com DT-16 + DT-07, ou `NEEDS_HUMAN` com o motivo."""

    alert_id: UUID
    state: AlertState
    features: InvestigationFeatures | None = None
    investigation: InvestigationOutput | None = None
    discarded_evidence_ids: list[NonEmptyStr] = []
    failure_reason: NonEmptyStr | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.state not in (AlertState.INVESTIGATING, AlertState.NEEDS_HUMAN):
            raise ValueError("InvestigationResult.state deve ser INVESTIGATING ou NEEDS_HUMAN")
        if (self.state is AlertState.NEEDS_HUMAN) != (self.failure_reason is not None):
            raise ValueError("failure_reason existe se e somente se state é NEEDS_HUMAN")
        if self.state is AlertState.INVESTIGATING and (self.features is None or self.investigation is None):
            raise ValueError("INVESTIGATING exige features e investigation")
        return self


def _needs_human(alert_id: UUID, motivo: str, features: InvestigationFeatures | None = None) -> InvestigationResult:
    return InvestigationResult(
        alert_id=alert_id, state=AlertState.NEEDS_HUMAN, features=features, failure_reason=motivo
    )


def _registrar_evento(alert_id: UUID, prompt_sha256: str, resposta: RespostaModelo, tentativa: int) -> None:
    """`TOOL_CALLED`/evento de modelo (RF-11): nunca grava prompt nem resposta, só o hash. Best-effort (T1.1)."""
    try:
        add_event(
            alert_id=str(alert_id),
            event_type="MODEL_CALLED",
            event_key=f"{alert_id}_investigation_{tentativa}",
            actor=Role.SISTEMA,
            model_id=resposta.model_id,
            prompt_sha256=prompt_sha256,
            prompt_version=PROMPT_VERSION,
            tokens_in=resposta.tokens_in,
            tokens_out=resposta.tokens_out,
            latency_ms=resposta.latency_ms,
        )
    except Exception:  # noqa: BLE001 - falha de auditoria não bloqueia a investigação (mesmo padrão do T1.3)
        pass


def run_investigation(
    sanitized_alert: SanitizedAlert,
    triage: TriageDecision,
    *,
    triage_rules: TriageRulesConfig | None = None,
    litellm_config: LiteLLMConfig | None = None,
    saml_mapping: SamlDMapping | None = None,
    history_fetcher: HistoryFetcher = get_customer_history,
    restriction_checker: RestrictionChecker = check_restriction_lists,
    contador: ContadorChamadas | None = None,
    **model_overrides: object,
) -> InvestigationResult:
    """Executa o pré-passo (DT-16) e a chamada LLM (DT-07) de um alerta com `TriageLevel.INVESTIGAR`."""
    if triage.level is not TriageLevel.INVESTIGAR:
        raise ValueError("run_investigation só se aplica a TriageLevel.INVESTIGAR (AGENTS.md §1)")

    contador = contador or ContadorChamadas()
    mapping = saml_mapping or load_saml_d_mapping()
    params = resolver_params(litellm_config)

    try:
        features = calcular_indicadores(
            sanitized_alert,
            rules=triage_rules,
            history_fetcher=history_fetcher,
            restriction_checker=restriction_checker,
        )
    except MCPIndisponivelError as exc:
        return _needs_human(sanitized_alert.alert_id, f"Pré-passo indisponível: {exc}")

    detectores = [regra.rule_id for regra in triage.fired_rules]
    prompt = montar_prompt(params.model, sanitized_alert, detectores, features.features)
    if not prompt.dentro_do_teto:
        return _needs_human(
            sanitized_alert.alert_id,
            f"Prompt com {prompt.tokens} tokens acima do teto de 300 mesmo sem F14+ (RF-05)",
            features=features,
        )

    schema = schema_geracao([f.feature_id for f in prompt.features])
    prompt_sha256 = hashlib.sha256(prompt.texto.encode("utf-8")).hexdigest()
    saida: InvestigationOutput | None = None
    for tentativa in range(1, MAX_RETRIES + 2):
        resposta = chamar_modelo(params, prompt.texto, schema, contador, **model_overrides)
        saida = validar_saida(resposta.texto)
        _registrar_evento(sanitized_alert.alert_id, prompt_sha256, resposta, tentativa)
        if saida is not None:
            break
    if saida is None:
        return _needs_human(sanitized_alert.alert_id, "JSON inválido após os retries (RF-05)", features=features)

    descartadas = missing_evidence_ids(saida, features)
    if descartadas:
        mantidas = [fid for fid in saida.evidence_feature_ids if fid not in descartadas]
        saida = saida.model_copy(update={"evidence_feature_ids": mantidas})

    criticas = {item.typology for item in mapping.tipologias.values() if item.critica}
    tipologia_critica = saida.typology_hypothesis in criticas
    detector_critico = any(regra.critical for regra in triage.fired_rules)
    if saida.recommendation is Recommendation.ARQUIVAR and (detector_critico or tipologia_critica):
        return InvestigationResult(
            alert_id=sanitized_alert.alert_id,
            state=AlertState.NEEDS_HUMAN,
            features=features,
            investigation=saida,
            discarded_evidence_ids=descartadas,
            failure_reason="Detector crítico ou tipologia crítica com recomendação ARQUIVAR (RF-05)",
        )

    return InvestigationResult(
        alert_id=sanitized_alert.alert_id,
        state=AlertState.INVESTIGATING,
        features=features,
        investigation=saida,
        discarded_evidence_ids=descartadas,
    )
