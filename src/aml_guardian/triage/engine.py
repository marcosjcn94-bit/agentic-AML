"""Motor da triagem inicial (T1.4, RF-03): executa os 4 detectores críticos e decide `TRIAGED` ou `NEEDS_HUMAN`.

MCP-02 indisponível (exceção ou resposta sem `status: success`) impede a triagem inteira: sem o detector de lista
de restrição não há garantia de "nenhum crítico disparado", então o alerta MUST ir para `NEEDS_HUMAN`, nunca
para `PROPOR_ARQUIVAMENTO` (AGENTS.md §2.2).
"""

from __future__ import annotations

from typing import Protocol, Self
from uuid import UUID

from pydantic import model_validator

from aml_guardian.config.triage import TriageRulesConfig, load_triage_rules
from aml_guardian.contracts.ingestion import AlertState, NonEmptyStr, SanitizedAlert, TriageLevel, _Contract
from aml_guardian.contracts.pipeline import FiredRule, TriageDecision
from aml_guardian.mcp_servers.server import check_restriction_lists
from aml_guardian.triage.detectors import (
    detect_camadas,
    detect_especie_depois_exterior,
    detect_fragmentacao,
    detect_lista_restricao,
)


class RestrictionChecker(Protocol):
    """Assinatura de MCP-02 `check_restriction_lists` (injetável para teste e para o cliente MCP real)."""

    def __call__(self, customer_id: str, cpf_cnpj_token: str | None = None) -> dict[str, object]: ...


class MCPIndisponivelError(RuntimeError):
    """MCP-02 fora do ar, com timeout ou com resposta fora do formato esperado (RF-03, AGENTS.md §2.2)."""


class TriageResult(_Contract):
    """Resultado do nó Triagem: `TRIAGED` com `TriageDecision` (DT-06), ou `NEEDS_HUMAN` sem MCP-02 disponível."""

    alert_id: UUID
    state: AlertState
    decision: TriageDecision | None = None
    failure_reason: NonEmptyStr | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.state not in (AlertState.TRIAGED, AlertState.NEEDS_HUMAN):
            raise ValueError("TriageResult.state deve ser TRIAGED ou NEEDS_HUMAN")
        if (self.state is AlertState.TRIAGED) == (self.decision is None):
            raise ValueError("decision existe se e somente se state é TRIAGED")
        if (self.state is AlertState.NEEDS_HUMAN) != (self.failure_reason is not None):
            raise ValueError("failure_reason existe se e somente se state é NEEDS_HUMAN")
        return self


def _consulta_mcp02(alert: SanitizedAlert, checker: RestrictionChecker) -> dict[str, object]:
    resultado = checker(customer_id=alert.sender_account, cpf_cnpj_token=alert.sender_customer.cpf_cnpj)
    if not isinstance(resultado, dict) or resultado.get("status") != "success":
        raise MCPIndisponivelError(f"MCP-02 respondeu fora do formato esperado: {resultado!r}")
    return resultado


def run_triage(
    sanitized_alert: SanitizedAlert,
    rules: TriageRulesConfig | None = None,
    restriction_checker: RestrictionChecker = check_restriction_lists,
) -> TriageResult:
    """Executa os 4 detectores críticos do RF-03 e decide `TRIAGED` (DT-06) ou `NEEDS_HUMAN`."""
    cfg = rules or load_triage_rules()
    detectores = cfg.detectores_criticos

    try:
        resultado_mcp02 = _consulta_mcp02(sanitized_alert, restriction_checker)
    except Exception as exc:  # noqa: BLE001 - qualquer falha do MCP-02 é indisponibilidade (AGENTS.md §2.2)
        return TriageResult(
            alert_id=sanitized_alert.alert_id,
            state=AlertState.NEEDS_HUMAN,
            failure_reason=f"MCP-02 indisponível na triagem: {exc}",
        )

    fired_rules: list[FiredRule] = [
        rule
        for rule in (
            detect_fragmentacao(sanitized_alert, detectores.fragmentacao),
            detect_camadas(sanitized_alert, detectores.camadas),
            detect_especie_depois_exterior(sanitized_alert, detectores.especie_depois_exterior),
            detect_lista_restricao(resultado_mcp02, detectores.lista_restricao),
        )
        if rule is not None
    ]
    level = TriageLevel.INVESTIGAR if fired_rules else TriageLevel.PROPOR_ARQUIVAMENTO
    decision = TriageDecision(
        alert_id=sanitized_alert.alert_id,
        level=level,
        fired_rules=fired_rules,
        rules_version=cfg.rules_version,
    )
    return TriageResult(alert_id=sanitized_alert.alert_id, state=AlertState.TRIAGED, decision=decision)
