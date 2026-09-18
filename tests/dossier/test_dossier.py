"""Testes da montagem do dossiê (T1.9, RF-08): snapshot COS/ARQUIVAMENTO, DT-11 válido e NEEDS_HUMAN."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from aml_guardian.contracts.ingestion import AlertState, TriageLevel
from aml_guardian.contracts.pipeline import (
    Citation,
    DossierType,
    Feature,
    InvestigationFeatures,
    InvestigationOutput,
    Recommendation,
    ReviewVerdict,
    TriageDecision,
    Typology,
)
from aml_guardian.deadlines.calculator import calculate_deadlines
from aml_guardian.dossier.assembler import assemble_from_investigation, assemble_from_triage
from aml_guardian.dossier.renderer import render_dossier

ALERT_ID = UUID("00000000-0000-0000-0000-000000000001")
DOSSIER_ID = UUID("00000000-0000-0000-0000-0000000000d1")
NOW = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
DEADLINES = calculate_deadlines(NOW)


def _features() -> InvestigationFeatures:
    return InvestigationFeatures(
        alert_id=ALERT_ID,
        features=[
            Feature(feature_id="F01", name="tx_janela", value=5, transaction_ids=["tx-1", "tx-2"]),
            Feature(feature_id="F03", name="abaixo_limiar", value=5, transaction_ids=["tx-1"]),
        ],
        features_version=1,
    )


def _citation() -> Citation:
    return Citation(
        chunk_id="CC4001:art1/i1/d:v1",
        article_ref="CC4001/art1/i1/d",
        quoted_text="Fragmentação de depósitos em espécie para dissimular o valor total da movimentação.",
        applicability="Fragmentação de depósitos ou saques para dissimular o valor total (art. 1º, I, d).",
    )


def _investigation(recommendation: Recommendation) -> InvestigationOutput:
    return InvestigationOutput(
        typology_hypothesis=Typology.STRUCTURING,
        confidence=0.82,
        recommendation=recommendation,
        evidence_feature_ids=["F01", "F03"],
    )


class TestAssembleFromTriage:
    def test_arquivamento_por_triagem_e_dt11_valido(self):
        triage = TriageDecision(
            alert_id=ALERT_ID, level=TriageLevel.PROPOR_ARQUIVAMENTO, fired_rules=[], rules_version=1
        )
        resultado = assemble_from_triage(ALERT_ID, triage, DEADLINES, dossier_id=DOSSIER_ID)

        assert resultado.state == AlertState.DRAFT_READY
        assert resultado.dossier.type == DossierType.ARQUIVAMENTO
        assert resultado.dossier.typology is None
        assert resultado.dossier.ai_generated_fields == []
        assert resultado.dossier.versions.corpus is None  # só rules é gravado no caminho da triagem

    def test_snapshot_arquivamento_por_triagem(self):
        triage = TriageDecision(
            alert_id=ALERT_ID, level=TriageLevel.PROPOR_ARQUIVAMENTO, fired_rules=[], rules_version=1
        )
        resultado = assemble_from_triage(ALERT_ID, triage, DEADLINES, dossier_id=DOSSIER_ID)

        assert resultado.rendered_text == (
            "# Arquivamento\n\n"
            f"**Alerta:** {ALERT_ID}\n"
            f"**Dossiê:** {DOSSIER_ID}\n"
            "**Status:** DRAFT_READY\n\n"
            "## Resumo\n"
            "Arquivamento proposto pela triagem determinística (rules_version 1): "
            "nenhum detector crítico disparado.\n\n"
            "## Origem\n"
            "Arquivamento proposto pela triagem determinística, sem investigação (RF-03): "
            "nenhum detector crítico disparado.\n\n"
            "## Prazos\n"
            f"- Seleção: {DEADLINES.selecao_em.isoformat()}\n"
            f"- Prazo interno: {DEADLINES.prazo_interno.isoformat()}\n"
            f"- Prazo regulatório de análise: {DEADLINES.prazo_regulatorio_analise.isoformat()}\n\n"
            "## Versões\n"
            "- Regras: 1"
        )


class TestAssembleFromInvestigationCOS:
    def test_cos_com_citacao_verificada_e_dt11_valido(self):
        review = ReviewVerdict(verified_citations=[_citation()], rejected_citations=[], grounding_raw_ratio=1.0)
        resultado = assemble_from_investigation(
            ALERT_ID,
            _investigation(Recommendation.COMUNICAR),
            _features(),
            review,
            cc4001_incisos=["I", "IV"],
            deadlines=DEADLINES,
            rules_version=1,
            corpus_version="corpus-v1",
            mapping_version=2,
            prompt_version="prompt-v1",
            model_id="qwen2.5:1.5b",
            dossier_id=DOSSIER_ID,
        )

        assert resultado.state == AlertState.DRAFT_READY
        assert resultado.dossier.type == DossierType.COS
        assert len(resultado.dossier.ai_generated_fields) == 4
        assert resultado.dossier.citations == [_citation()]

    def test_snapshot_cos_inclui_citacao_e_marca_gerado_por_ia(self):
        review = ReviewVerdict(verified_citations=[_citation()], rejected_citations=[], grounding_raw_ratio=1.0)
        resultado = assemble_from_investigation(
            ALERT_ID,
            _investigation(Recommendation.COMUNICAR),
            _features(),
            review,
            cc4001_incisos=["I", "IV"],
            deadlines=DEADLINES,
            rules_version=1,
            corpus_version="corpus-v1",
            mapping_version=2,
            prompt_version="prompt-v1",
            model_id="qwen2.5:1.5b",
            dossier_id=DOSSIER_ID,
        )

        assert "# Comunicação de Operação Suspeita (COS)" in resultado.rendered_text
        assert "## Tipologia (gerado por IA)\nStructuring" in resultado.rendered_text
        assert 'CC4001/art1/i1/d**: "Fragmentação de depósitos' in resultado.rendered_text
        assert "## Recomendação (gerado por IA)\nCOMUNICAR" in resultado.rendered_text
        assert "typology_hypothesis, confidence, recommendation, evidence_feature_ids" in resultado.rendered_text

    def test_cos_sem_citacao_verificada_vai_para_needs_human(self):
        review = ReviewVerdict(verified_citations=[], rejected_citations=[], grounding_raw_ratio=0.0)
        resultado = assemble_from_investigation(
            ALERT_ID,
            _investigation(Recommendation.COMUNICAR),
            _features(),
            review,
            cc4001_incisos=["I", "IV"],
            deadlines=DEADLINES,
            rules_version=1,
            corpus_version="corpus-v1",
            mapping_version=2,
            prompt_version="prompt-v1",
            model_id="qwen2.5:1.5b",
        )
        assert resultado.state == AlertState.NEEDS_HUMAN
        assert resultado.dossier is None
        assert "NEEDS_HUMAN" in resultado.failure_reason


class TestAssembleFromInvestigationArquivamento:
    def test_arquivar_investigado_e_dt11_valido(self):
        review = ReviewVerdict(verified_citations=[], rejected_citations=[], grounding_raw_ratio=0.0)
        resultado = assemble_from_investigation(
            ALERT_ID,
            _investigation(Recommendation.ARQUIVAR),
            _features(),
            review,
            cc4001_incisos=["I", "IV"],
            deadlines=DEADLINES,
            rules_version=1,
            corpus_version="corpus-v1",
            mapping_version=2,
            prompt_version="prompt-v1",
            model_id="qwen2.5:1.5b",
            dossier_id=DOSSIER_ID,
        )
        assert resultado.state == AlertState.DRAFT_READY
        assert resultado.dossier.type == DossierType.ARQUIVAMENTO
        assert resultado.dossier.typology == Typology.STRUCTURING  # investigado: preenche tipologia
        assert len(resultado.dossier.ai_generated_fields) == 4


class TestInconclusivo:
    def test_inconclusivo_vai_para_needs_human(self):
        review = ReviewVerdict(verified_citations=[], rejected_citations=[], grounding_raw_ratio=0.0)
        resultado = assemble_from_investigation(
            ALERT_ID,
            _investigation(Recommendation.INCONCLUSIVO),
            _features(),
            review,
            cc4001_incisos=[],
            deadlines=DEADLINES,
            rules_version=1,
            corpus_version="corpus-v1",
            mapping_version=2,
            prompt_version="prompt-v1",
            model_id="qwen2.5:1.5b",
        )
        assert resultado.state == AlertState.NEEDS_HUMAN
        assert resultado.dossier is None
        assert "INCONCLUSIVO" in resultado.failure_reason


class TestCampoObrigatorioAusente:
    def test_prompt_version_vazio_vai_para_needs_human(self):
        review = ReviewVerdict(verified_citations=[_citation()], rejected_citations=[], grounding_raw_ratio=1.0)
        resultado = assemble_from_investigation(
            ALERT_ID,
            _investigation(Recommendation.COMUNICAR),
            _features(),
            review,
            cc4001_incisos=["I", "IV"],
            deadlines=DEADLINES,
            rules_version=1,
            corpus_version="corpus-v1",
            mapping_version=2,
            prompt_version="",  # campo obrigatório (DT-11 versions.prompt) ausente
            model_id="qwen2.5:1.5b",
        )
        assert resultado.state == AlertState.NEEDS_HUMAN
        assert resultado.dossier is None
        assert resultado.failure_reason is not None


class TestRenderizacaoSegura:
    def test_conteudo_interpretavel_como_html_e_escapado(self):
        review = ReviewVerdict(
            verified_citations=[_citation().model_copy(update={"quoted_text": "<script>alert(1)</script>"})],
            rejected_citations=[],
            grounding_raw_ratio=1.0,
        )
        resultado = assemble_from_investigation(
            ALERT_ID,
            _investigation(Recommendation.COMUNICAR),
            _features(),
            review,
            cc4001_incisos=["I"],
            deadlines=DEADLINES,
            rules_version=1,
            corpus_version="corpus-v1",
            mapping_version=2,
            prompt_version="prompt-v1",
            model_id="qwen2.5:1.5b",
            dossier_id=DOSSIER_ID,
        )

        assert resultado.dossier is not None
        rendered = render_dossier(resultado.dossier)
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered
        assert "## Recomenda\u00e7\u00e3o (gerado por IA)" in rendered
