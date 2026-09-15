"""Contratos de triagem, investigação, normas e dossiê: DT-06 a DT-11 e DT-16 (SPEC.md §8.2, RF-03 a RF-09).

Nenhum destes contratos admite dado pessoal em claro: contas aparecem só como token `<TIPO>_<NN>`.
DT-08 e DT-09 carregam texto normativo público, preservado sem normalização (o Revisor normaliza para o hash).
"""

from __future__ import annotations

from collections import Counter
from enum import StrEnum
from typing import Annotated, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, HttpUrl, StrictBool, StrictInt, StringConstraints, model_validator

from aml_guardian.contracts.ingestion import AlertState, NonEmptyStr, TriageLevel, _Contract

MAX_EVIDENCE = 3
MAX_APPLICABILITY_CHARS = 300

FeatureId = Annotated[str, StringConstraints(pattern=r"^F\d{2,}$")]
Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Inciso = Annotated[str, StringConstraints(pattern=r"^[IVXLC]+$")]
VersionNumber = Annotated[int, Field(strict=True, ge=1)]
Ratio = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]
NormText = Annotated[str, StringConstraints(pattern=r"\S")]
Applicability = Annotated[str, StringConstraints(pattern=r"\S", max_length=MAX_APPLICABILITY_CHARS)]


class Typology(StrEnum):
    """Hipótese de tipologia do DT-07: 17 rótulos suspeitos do SAML-D (SPEC.md §3.2) + `NENHUMA` (AGENTS.md §4.2)."""

    FAN_OUT = "Fan-Out"
    FAN_IN = "Fan-In"
    CYCLE = "Cycle"
    BIPARTITE = "Bipartite"
    STACKED_BIPARTITE = "Stacked Bipartite"
    SCATTER_GATHER = "Scatter-Gather"
    GATHER_SCATTER = "Gather-Scatter"
    LAYERED_FAN_IN = "Layered Fan-In"
    LAYERED_FAN_OUT = "Layered Fan-Out"
    STRUCTURING = "Structuring"
    SMURFING = "Smurfing"
    OVER_INVOICING = "Over-Invoicing"
    DEPOSIT_SEND = "Deposit-Send"
    CASH_WITHDRAWAL = "Cash Withdrawal"
    SINGLE_LARGE_TRANSACTION = "Single Large Transaction"
    BEHAVIOURAL_CHANGE_1 = "Behavioural Change 1"
    BEHAVIOURAL_CHANGE_2 = "Behavioural Change 2"
    NENHUMA = "NENHUMA"


class Recommendation(StrEnum):
    """Recomendação do nó Investigação (DT-07, RF-05)."""

    COMUNICAR = "COMUNICAR"
    ARQUIVAR = "ARQUIVAR"
    INCONCLUSIVO = "INCONCLUSIVO"


class DossierType(StrEnum):
    """Tipo do dossiê (DT-11, RF-08)."""

    COS = "COS"
    ARQUIVAMENTO = "ARQUIVAMENTO"


class AiGeneratedField(StrEnum):
    """Campos do DT-07 decididos pelo LLM e marcados "gerado por IA" no dossiê (RF-08)."""

    TYPOLOGY_HYPOTHESIS = "typology_hypothesis"
    CONFIDENCE = "confidence"
    RECOMMENDATION = "recommendation"
    EVIDENCE_FEATURE_IDS = "evidence_feature_ids"


class FiredRule(_Contract):
    """Regra disparada na triagem (DT-06)."""

    rule_id: NonEmptyStr
    description: NonEmptyStr
    critical: StrictBool


class TriageDecision(_Contract):
    """DT-06 — decisão da triagem determinística por regra versionada (RF-03)."""

    alert_id: UUID
    level: TriageLevel
    fired_rules: list[FiredRule]
    rules_version: VersionNumber

    @model_validator(mode="after")
    def _no_archive_with_critical_rule(self) -> Self:
        if self.level is TriageLevel.PROPOR_ARQUIVAMENTO and any(rule.critical for rule in self.fired_rules):
            raise ValueError("PROPOR_ARQUIVAMENTO com detector crítico disparado (RF-03)")
        return self


class InvestigationOutput(_Contract):
    """DT-07 — saída expandida do nó Investigação (RF-05); pertinência ao DT-16 via `missing_evidence_ids`."""

    typology_hypothesis: Typology
    confidence: Ratio
    recommendation: Recommendation
    evidence_feature_ids: list[FeatureId] = Field(max_length=MAX_EVIDENCE)


class Feature(_Contract):
    """Indicador agregado do DT-16 com as transações que o compõem (AGENTS.md §4.3)."""

    feature_id: FeatureId
    name: NonEmptyStr
    value: StrictInt | NonEmptyStr
    transaction_ids: list[NonEmptyStr]


def _duplicates(values: list[str]) -> list[str]:
    return [value for value, count in Counter(values).items() if count > 1]


class InvestigationFeatures(_Contract):
    """DT-16 — indicadores calculados por código que o LLM recebe no lugar das transações (RF-05, ADR-013)."""

    alert_id: UUID
    features: list[Feature] = Field(min_length=1)
    features_version: VersionNumber

    @model_validator(mode="after")
    def _unique_feature_ids(self) -> Self:
        if duplicated := _duplicates([feature.feature_id for feature in self.features]):
            raise ValueError(f"feature_id duplicado no DT-16: {duplicated}")
        return self


def missing_evidence_ids(investigation: InvestigationOutput, features: InvestigationFeatures) -> list[str]:
    """Evidências do DT-07 ausentes do DT-16, na ordem original; o nó Investigação as descarta e registra (RF-05)."""
    known = {feature.feature_id for feature in features.features}
    return [feature_id for feature_id in investigation.evidence_feature_ids if feature_id not in known]


class NormChunk(_Contract):
    """DT-08 — trecho normativo por dispositivo, com `text_sha256` do texto normalizado (RF-14)."""

    chunk_id: NonEmptyStr
    doc_id: NonEmptyStr
    article_ref: NonEmptyStr
    text: NormText
    text_sha256: Sha256Hex
    corpus_version: NonEmptyStr
    source_url: HttpUrl


class Citation(_Contract):
    """DT-09 — citação escolhida sem LLM; `quoted_text` copiado do chunk e `applicability` do mapeamento (RF-06)."""

    chunk_id: NonEmptyStr
    article_ref: NonEmptyStr
    quoted_text: NormText
    applicability: Applicability


class RejectedCitation(_Contract):
    """Citação removida pelo Revisor com o motivo (DT-10)."""

    chunk_id: NonEmptyStr
    reason: NonEmptyStr


class ReviewVerdict(_Contract):
    """DT-10 — veredito determinístico do Revisor sobre as citações da minuta (RF-07, RNF-02)."""

    verified_citations: list[Citation]
    rejected_citations: list[RejectedCitation]
    grounding_raw_ratio: Ratio

    @model_validator(mode="after")
    def _verified_and_rejected_disjoint(self) -> Self:
        verified = {citation.chunk_id for citation in self.verified_citations}
        if both := sorted(verified.intersection(c.chunk_id for c in self.rejected_citations)):
            raise ValueError(f"chunk_id verificado e rejeitado ao mesmo tempo: {both}")
        return self


class DossierDeadlines(_Contract):
    """Prazos do dossiê (RF-09, SPEC.md §3.1); o cálculo fica no nó Dossiê + Prazo."""

    selecao_em: AwareDatetime
    prazo_interno: AwareDatetime
    prazo_regulatorio_analise: AwareDatetime

    @model_validator(mode="after")
    def _chronological(self) -> Self:
        if not self.selecao_em <= self.prazo_interno <= self.prazo_regulatorio_analise:
            raise ValueError("deadlines fora de ordem: selecao_em ≤ prazo_interno ≤ prazo_regulatorio_analise")
        return self


class DossierVersions(_Contract):
    """Versões gravadas no dossiê (AGENTS.md §2.7); só `rules` existe no caminho `PROPOR_ARQUIVAMENTO`."""

    rules: VersionNumber
    corpus: NonEmptyStr | None
    mapping: VersionNumber | None
    features: VersionNumber | None
    prompt: NonEmptyStr | None
    model: NonEmptyStr | None


class Dossier(_Contract):
    """DT-11 — minuta montada por template, sem texto livre de LLM e sem dado pessoal (RF-08, ADR-013)."""

    dossier_id: UUID
    alert_id: UUID
    type: DossierType
    summary: NonEmptyStr
    typology: Typology | None
    cc4001_incisos: list[Inciso]
    evidence: list[Feature] = Field(max_length=MAX_EVIDENCE)
    citations: list[Citation]
    recommendation: Recommendation
    ai_generated_fields: list[AiGeneratedField]
    deadlines: DossierDeadlines
    versions: DossierVersions
    status: AlertState

    @model_validator(mode="after")
    def _type_matches_recommendation(self) -> Self:
        """`INCONCLUSIVO` não vira dossiê: segue para `NEEDS_HUMAN` (RF-08)."""
        if _RECOMMENDATION_BY_TYPE[self.type] is not self.recommendation:
            raise ValueError(f"dossiê {self.type} incoerente com recomendação {self.recommendation} (RF-08)")
        return self

    @model_validator(mode="after")
    def _cos_has_verified_citation(self) -> Self:
        if self.type is DossierType.COS and not self.citations:
            raise ValueError("dossiê COS sem citação verificada vai para NEEDS_HUMAN (RF-07)")
        return self

    @model_validator(mode="after")
    def _status_is_dossier_state(self) -> Self:
        if self.status not in _DOSSIER_STATES:
            raise ValueError(f"{self.status} não é estado de dossiê (RF-10)")
        return self

    @model_validator(mode="after")
    def _path_is_coherent(self) -> Self:
        """Investigado: os 4 campos de IA, tipologia e todas as versões. Triagem: nenhum artefato de investigação."""
        if len(self.ai_generated_fields) != len(set(self.ai_generated_fields)):
            raise ValueError("ai_generated_fields com item repetido")
        if set(self.ai_generated_fields) == set(AiGeneratedField):
            if self.typology is None:
                raise ValueError("dossiê investigado exige typology (RF-08)")
            if missing := [name for name, value in self.versions if value is None]:
                raise ValueError(f"dossiê investigado sem versões {missing} (AGENTS.md §2.7)")
            return self
        if self.ai_generated_fields:
            raise ValueError("ai_generated_fields deve listar os 4 campos do DT-07 ou nenhum (RF-08)")
        has_investigation = self.typology is not None or self.cc4001_incisos or self.evidence or self.citations
        if self.type is not DossierType.ARQUIVAMENTO or has_investigation:
            raise ValueError("dossiê da triagem admite só ARQUIVAMENTO sem tipologia, incisos, evidência ou citação")
        if any(value is not None for name, value in self.versions if name != "rules"):
            raise ValueError("dossiê da triagem grava só versions.rules")
        return self


_RECOMMENDATION_BY_TYPE = {DossierType.COS: Recommendation.COMUNICAR, DossierType.ARQUIVAMENTO: Recommendation.ARQUIVAR}
_DOSSIER_STATES = frozenset({AlertState.DRAFT_READY, AlertState.SUBMITTED, AlertState.APPROVED, AlertState.RETURNED})
