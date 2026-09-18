"""Montagem do dossiê por template Jinja2 (T1.9, RF-08): sem texto livre de LLM, só citações verificadas.

Dois caminhos do RF-10: arquivamento pela triagem (sem investigação) e o caminho investigado (`COS` ou
arquivamento pela recomendação da Investigação). `INCONCLUSIVO` e qualquer falha de validação do DT-11 (campo
obrigatório ausente, `COS` sem citação verificada) viram `NEEDS_HUMAN`, preservando o motivo (RF-08, RF-10).
"""

from __future__ import annotations

from typing import Any, Self
from uuid import UUID, uuid4

from pydantic import ValidationError, model_validator

from aml_guardian.contracts.ingestion import AlertState, NonEmptyStr, _Contract
from aml_guardian.contracts.pipeline import (
    AiGeneratedField,
    Dossier,
    DossierDeadlines,
    DossierType,
    DossierVersions,
    Inciso,
    InvestigationFeatures,
    InvestigationOutput,
    Recommendation,
    ReviewVerdict,
    TriageDecision,
)
from aml_guardian.dossier.renderer import render_dossier

_DOSSIER_STATE = AlertState.DRAFT_READY


class DossierResult(_Contract):
    """Resultado da montagem: `DRAFT_READY` com dossiê e texto renderizado, ou `NEEDS_HUMAN` com o motivo."""

    alert_id: UUID
    state: AlertState
    dossier: Dossier | None = None
    rendered_text: NonEmptyStr | None = None
    failure_reason: NonEmptyStr | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.state not in (_DOSSIER_STATE, AlertState.NEEDS_HUMAN):
            raise ValueError("DossierResult.state deve ser DRAFT_READY ou NEEDS_HUMAN")
        tem_dossier = self.dossier is not None and self.rendered_text is not None
        if (self.state is _DOSSIER_STATE) != tem_dossier:
            raise ValueError("dossier/rendered_text existem se e somente se state é DRAFT_READY")
        if (self.state is AlertState.NEEDS_HUMAN) != (self.failure_reason is not None):
            raise ValueError("failure_reason existe se e somente se state é NEEDS_HUMAN")
        return self


def _build(alert_id: UUID, dossier_id: UUID | None, versions: dict[str, Any], **campos: Any) -> DossierResult:
    try:
        # DossierVersions também é construído dentro do try: um campo de versão ausente/vazio (DT-11) é a mesma
        # falha de "campo obrigatório ausente" que uma falha de validação do próprio Dossier (RF-08).
        dossier = Dossier(
            dossier_id=dossier_id or uuid4(), alert_id=alert_id, versions=DossierVersions(**versions), **campos
        )
    except ValidationError as exc:
        return DossierResult(alert_id=alert_id, state=AlertState.NEEDS_HUMAN, failure_reason=str(exc))
    return DossierResult(
        alert_id=alert_id, state=_DOSSIER_STATE, dossier=dossier, rendered_text=render_dossier(dossier)
    )


def assemble_from_triage(
    alert_id: UUID,
    triage: TriageDecision,
    deadlines: DossierDeadlines,
    dossier_id: UUID | None = None,
) -> DossierResult:
    """Caminho `PROPOR_ARQUIVAMENTO`: dossiê de arquivamento por template, sem investigação e sem LLM (RF-03/RF-08)."""
    summary = (
        f"Arquivamento proposto pela triagem determinística (rules_version {triage.rules_version}): "
        "nenhum detector crítico disparado."
    )
    return _build(
        alert_id,
        dossier_id,
        type=DossierType.ARQUIVAMENTO,
        summary=summary,
        typology=None,
        cc4001_incisos=[],
        evidence=[],
        citations=[],
        recommendation=Recommendation.ARQUIVAR,
        ai_generated_fields=[],
        deadlines=deadlines,
        versions={
            "rules": triage.rules_version,
            "corpus": None,
            "mapping": None,
            "features": None,
            "prompt": None,
            "model": None,
        },
        status=_DOSSIER_STATE,
    )


def assemble_from_investigation(
    alert_id: UUID,
    investigation: InvestigationOutput,
    features: InvestigationFeatures,
    review: ReviewVerdict,
    cc4001_incisos: list[Inciso],
    deadlines: DossierDeadlines,
    rules_version: int,
    corpus_version: str,
    mapping_version: int,
    prompt_version: str,
    model_id: str,
    dossier_id: UUID | None = None,
) -> DossierResult:
    """Caminho investigado: `COS` (COMUNICAR) ou `ARQUIVAMENTO` (ARQUIVAR); `INCONCLUSIVO` vai a `NEEDS_HUMAN`."""
    if investigation.recommendation is Recommendation.INCONCLUSIVO:
        return DossierResult(
            alert_id=alert_id,
            state=AlertState.NEEDS_HUMAN,
            failure_reason="recomendação INCONCLUSIVO não gera dossiê (RF-08)",
        )

    tipo = DossierType.COS if investigation.recommendation is Recommendation.COMUNICAR else DossierType.ARQUIVAMENTO
    conhecidas = {feature.feature_id: feature for feature in features.features}
    evidence = [conhecidas[fid] for fid in investigation.evidence_feature_ids if fid in conhecidas]
    summary = (
        f"Recomendação {investigation.recommendation.value}: hipótese {investigation.typology_hypothesis.value}, "
        f"confiança {investigation.confidence:.2f}, {len(review.verified_citations)} citação(ões) verificada(s)."
    )

    return _build(
        alert_id,
        dossier_id,
        type=tipo,
        summary=summary,
        typology=investigation.typology_hypothesis,
        cc4001_incisos=cc4001_incisos,
        evidence=evidence,
        citations=review.verified_citations,
        recommendation=investigation.recommendation,
        ai_generated_fields=list(AiGeneratedField),
        deadlines=deadlines,
        versions={
            "rules": rules_version,
            "corpus": corpus_version,
            "mapping": mapping_version,
            "features": features.features_version,
            "prompt": prompt_version,
            "model": model_id,
        },
        status=_DOSSIER_STATE,
    )
