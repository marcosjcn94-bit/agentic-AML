"""Contratos de execução: DT-12, DT-13, DT-15 e `InvestigationState` (SPEC.md §8.2, §9.3, RF-10 a RF-12).

DT-12, DT-15 e o estado do grafo não admitem dado pessoal: só enums, versões, hashes e contratos já sanitizados.
DT-13 é o único com dado pessoal, sempre sintético e gerado em tempo de execução. DT-14 fica em `envelope.py`.
"""

from __future__ import annotations

from datetime import date, timedelta, timezone
from enum import StrEnum
from typing import Annotated, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from aml_guardian.contracts.envelope import A2AEnvelope, Attempt, Node, alert_ids
from aml_guardian.contracts.ingestion import AlertState, NonEmptyStr, SanitizedAlert, TriageLevel, _Contract
from aml_guardian.contracts.pipeline import (
    Citation,
    Dossier,
    InvestigationFeatures,
    InvestigationOutput,
    ReviewVerdict,
    Sha256Hex,
    TriageDecision,
    VersionNumber,
    missing_evidence_ids,
)

# DT-14 é reexportado para que `runtime` exponha todos os contratos da T0.4.
__all__ = [
    "MIN_JUSTIFICATION_CHARS",
    "A2AEnvelope",
    "Approval",
    "ApprovalDecision",
    "AuditEvent",
    "Budget",
    "ExpectedEntity",
    "InvestigationState",
    "Role",
    "SanitizationTestCase",
]

MIN_JUSTIFICATION_CHARS = 50

Count = Annotated[int, Field(strict=True, ge=0)]
EventType = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9_]*$")]
EntityType = Annotated[str, StringConstraints(pattern=r"^[A-Z]+$")]
RawText = Annotated[str, StringConstraints(pattern=r"\S")]
Justification = Annotated[str, StringConstraints(strip_whitespace=True, min_length=MIN_JUSTIFICATION_CHARS)]


class Role(StrEnum):
    """Papéis do SPEC.md §9.1; `actor` do DT-12 é papel, nunca nome de pessoa."""

    SISTEMA = "sistema"
    ANALISTA = "analista"
    COMPLIANCE_OFFICER = "compliance_officer"


class ApprovalDecision(StrEnum):
    """Decisão do Compliance Officer (RF-12)."""

    COMUNICAR = "COMUNICAR"
    ARQUIVAR = "ARQUIVAR"
    DEVOLVER = "DEVOLVER"


class AuditEvent(_Contract):
    """DT-12 — evento append-only encadeado por hash; o prompt entra só como `prompt_sha256` (RF-11, ADR-008).

    Todos os campos do RF-11 são obrigatórios na entrada; os que não se aplicam ao evento vêm `null`.
    """

    seq: Attempt
    event_key: NonEmptyStr
    occurred_at: AwareDatetime
    alert_id: UUID
    event_type: EventType
    actor: Role
    state_from: AlertState | None
    state_to: AlertState | None
    model_id: NonEmptyStr | None
    prompt_sha256: Sha256Hex | None
    rules_version: VersionNumber | None
    corpus_version: NonEmptyStr | None
    mapping_version: VersionNumber | None
    prompt_version: NonEmptyStr | None
    tokens_in: Count
    tokens_out: Count
    latency_ms: Count
    prev_hash: Sha256Hex | None
    hash: Sha256Hex

    @model_validator(mode="after")
    def _event_key_of_alert(self) -> Self:
        """`event_key = alert_id + node + attempt` (RF-10); aqui só se garante o prefixo do próprio alerta."""
        if not self.event_key.startswith(str(self.alert_id)):
            raise ValueError("event_key não começa pelo alert_id do evento (RF-10)")
        return self

    @model_validator(mode="after")
    def _chain_start(self) -> Self:
        if (self.seq == 1) != (self.prev_hash is None):
            raise ValueError("prev_hash é null só no primeiro evento da cadeia (seq = 1)")
        return self

    @model_validator(mode="after")
    def _transition_and_model_are_complete(self) -> Self:
        if self.state_from is not None and self.state_to is None:
            raise ValueError("state_from sem state_to")
        llm = (self.model_id, self.prompt_sha256, self.prompt_version)
        if any(value is None for value in llm) and any(value is not None for value in llm):
            raise ValueError("model_id, prompt_sha256 e prompt_version vêm juntos ou todos null (RF-11)")
        if self.model_id is None and (self.tokens_in or self.tokens_out):
            raise ValueError("tokens_in/tokens_out > 0 exigem model_id")
        return self


class ExpectedEntity(_Contract):
    """Entidade esperada no DT-13: tipo do token e intervalo `[start, end)` no texto."""

    type: EntityType
    start: Count
    end: Count

    @model_validator(mode="after")
    def _non_empty_span(self) -> Self:
        if self.start >= self.end:
            raise ValueError("entidade com start ≥ end")
        return self


class SanitizationTestCase(_Contract):
    """DT-13 — caso do conjunto de teste de sanitização (RF-02); texto sem normalização para preservar offsets."""

    text: RawText
    expected_entities: list[ExpectedEntity]

    @model_validator(mode="after")
    def _spans_inside_text_without_overlap(self) -> Self:
        spans = sorted((entity.start, entity.end) for entity in self.expected_entities)
        if spans and spans[-1][1] > len(self.text):
            raise ValueError("entidade além do fim do texto")
        if any(next_start < end for (_, end), (next_start, _) in zip(spans, spans[1:], strict=False)):
            raise ValueError("entidades sobrepostas")
        return self


class Approval(_Contract):
    """DT-15 — aceite do Compliance Officer com justificativa ≥ 50 caracteres (RF-12, art. 48, §1º)."""

    alert_id: UUID
    decision: ApprovalDecision
    justification: Justification
    decided_by_role: Role
    decided_at: AwareDatetime
    prazo_comunicacao: date | None

    @model_validator(mode="after")
    def _only_compliance_officer(self) -> Self:
        if self.decided_by_role is not Role.COMPLIANCE_OFFICER:
            raise ValueError("aceite exige o papel compliance_officer (RF-12)")
        return self

    @model_validator(mode="after")
    def _deadline_only_when_reporting(self) -> Self:
        """`prazo_comunicacao` é o próximo dia útil após `decided_at` e só existe em `COMUNICAR` (RF-09)."""
        if (self.decision is ApprovalDecision.COMUNICAR) != (self.prazo_comunicacao is not None):
            raise ValueError("prazo_comunicacao existe se e somente se decision = COMUNICAR (RF-09)")
        if self.prazo_comunicacao is None:
            return self
        if self.prazo_comunicacao <= self.decided_at.astimezone(BRASILIA).date():
            raise ValueError("prazo_comunicacao deve ser posterior à data da decisão em Brasília (RF-09)")
        if self.prazo_comunicacao.weekday() >= _SATURDAY:
            raise ValueError("prazo_comunicacao em fim de semana não é dia útil (RF-09)")
        return self


class Budget(_Contract):
    """Orçamento consumido pelo alerta (RF-10); excesso não é recusado aqui, leva a `NEEDS_HUMAN`."""

    tokens_used: Count
    started_at: AwareDatetime


class InvestigationState(_Contract):
    """Estado do grafo persistido no checkpoint (SPEC.md §9.3); `NEEDS_HUMAN` preserva o acumulado (RF-10)."""

    alert_id: UUID
    trace_id: UUID
    state: AlertState
    sanitized_alert: SanitizedAlert
    triage: TriageDecision | None = None
    features: InvestigationFeatures | None = None
    investigation: InvestigationOutput | None = None
    retrieved_chunk_ids: list[NonEmptyStr] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    review: ReviewVerdict | None = None
    dossier: Dossier | None = None
    budget: Budget
    attempts: dict[Node, Attempt] = Field(default_factory=dict)
    failure_reason: NonEmptyStr | None = None

    @model_validator(mode="after")
    def _single_alert(self) -> Self:
        if len(alert_ids(self)) > 1:
            raise ValueError("estado com contratos de alert_id diferentes")
        return self

    @model_validator(mode="after")
    def _investigation_grounded_in_features(self) -> Self:
        """DT-07 guardado já passou pelo descarte do RF-05: toda evidência pertence ao DT-16."""
        if self.investigation is None:
            return self
        if self.features is None or missing_evidence_ids(self.investigation, self.features):
            raise ValueError("investigation exige features contendo todas as evidências (RF-05)")
        return self

    @model_validator(mode="after")
    def _matches_state_machine(self) -> Self:
        """Coerência com o RF-10; `NEEDS_HUMAN` pode ocorrer em qualquer ponto e só exige `failure_reason`."""
        if self.state is AlertState.NEEDS_HUMAN:
            if self.failure_reason is None:
                raise ValueError("NEEDS_HUMAN exige failure_reason (RF-10)")
            return self
        if self.state is AlertState.RECEIVED:
            raise ValueError("o grafo começa após a sanitização (RECEIVED não tem sanitized_alert)")
        stage = _STAGE[self.state]
        if early := [name for name, first in _FIRST_STAGE.items() if getattr(self, name) and stage < first]:
            raise ValueError(f"{self.state} não admite artefato de fase posterior: {early} (RF-10)")
        if self.triage is None:
            if self.state is AlertState.SANITIZED:
                return self
            raise ValueError(f"{self.state} exige triage (RF-10)")
        investigated = self.triage.level is TriageLevel.INVESTIGAR
        if not investigated and any(getattr(self, name) for name in _INVESTIGATION_ARTIFACTS):
            raise ValueError("caminho PROPOR_ARQUIVAMENTO não admite artefato de investigação (AGENTS.md §2.7)")
        if self.state in _INVESTIGATION_STATES and not investigated:
            raise ValueError(f"{self.state} exige triagem INVESTIGAR (RF-10)")
        if self.state in _POST_INVESTIGATION_STATES and self.investigation is None:
            raise ValueError(f"{self.state} exige investigation (RF-10)")
        return self._dossier_matches_state(investigated)

    def _dossier_matches_state(self, investigated: bool) -> Self:
        if (self.dossier is not None) != (self.state in _DOSSIER_STATES):
            raise ValueError(f"dossier existe se e somente se o estado é de dossiê; estado {self.state} (RF-10)")
        if self.dossier is None:
            return self
        if self.dossier.status is not self.state:
            raise ValueError(f"dossier.status {self.dossier.status} diverge do estado {self.state}")
        if bool(self.dossier.ai_generated_fields) != investigated:
            raise ValueError("dossier incoerente com o caminho da triagem (RF-08)")
        return self


# Brasil sem horário de verão desde 2019: offset fixo evita depender de `tzdata` no Windows.
BRASILIA = timezone(timedelta(hours=-3), "America/Sao_Paulo")
_SATURDAY = 5

# Ordem das fases do RF-10 e primeira fase em que cada artefato pode existir (AGENTS.md §1).
_STAGE = {
    AlertState.SANITIZED: 0,
    AlertState.TRIAGED: 1,
    AlertState.INVESTIGATING: 2,
    AlertState.RESEARCHING: 3,
    AlertState.REVIEWING: 4,
    AlertState.DRAFT_READY: 5,
    AlertState.SUBMITTED: 5,
    AlertState.APPROVED: 5,
    AlertState.RETURNED: 5,
}
_FIRST_STAGE = {
    "triage": 1,
    "features": 2,
    "investigation": 2,
    "retrieved_chunk_ids": 3,
    "citations": 3,
    "review": 4,
    "dossier": 5,
}
_INVESTIGATION_ARTIFACTS = ("features", "investigation", "retrieved_chunk_ids", "citations", "review")
_INVESTIGATION_STATES = frozenset({AlertState.INVESTIGATING, AlertState.RESEARCHING, AlertState.REVIEWING})
_POST_INVESTIGATION_STATES = frozenset({AlertState.RESEARCHING, AlertState.REVIEWING})
_DOSSIER_STATES = frozenset({AlertState.DRAFT_READY, AlertState.SUBMITTED, AlertState.APPROVED, AlertState.RETURNED})
