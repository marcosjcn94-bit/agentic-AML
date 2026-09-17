"""Testes do Revisor determinístico (T1.8, RF-07): citação adulterada, chunk fora dos recuperados, COS sem citação."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from aml_guardian.contracts.ingestion import AlertState
from aml_guardian.contracts.pipeline import (
    AiGeneratedField,
    Citation,
    Dossier,
    DossierDeadlines,
    DossierType,
    DossierVersions,
    Recommendation,
    Typology,
)
from aml_guardian.norms.normalize import text_sha256
from aml_guardian.review.verifier import review_citations

CORPUS_VERSION = "v1"
CHUNK_ID = "CC4001:art1/i1/d:v1"
ORIGINAL_TEXT = "Fragmentação de depósitos em espécie para dissimular o valor total da movimentação."
CANONICAL_SHA = text_sha256(ORIGINAL_TEXT)
NOW = datetime.now(UTC)


def _fake_getter():
    def getter(chunk_id: str, corpus_version: str) -> dict[str, object]:
        if chunk_id != CHUNK_ID or corpus_version != CORPUS_VERSION:
            return {"error": "NOT_FOUND", "message": "fora da versão vigente", "retryable": False}
        return {"status": "success", "chunk_id": chunk_id, "text": ORIGINAL_TEXT, "text_sha256": CANONICAL_SHA}

    return getter


def _citation(quoted_text: str = ORIGINAL_TEXT, chunk_id: str = CHUNK_ID) -> Citation:
    return Citation(
        chunk_id=chunk_id,
        article_ref="CC4001/art1/i1/d",
        quoted_text=quoted_text,
        applicability="Fragmentação de depósitos ou saques para dissimular o valor total (art. 1º, I, d).",
    )


class TestCitacaoAdulterada:
    def test_um_caractere_adulterado_e_rejeitada(self):
        adulterada = _citation(quoted_text=ORIGINAL_TEXT.replace("depósitos", "depOsitos"))
        verdict = review_citations(
            [adulterada], retrieved_chunk_ids=[CHUNK_ID], corpus_version=CORPUS_VERSION, passage_getter=_fake_getter()
        )
        assert verdict.verified_citations == []
        assert verdict.rejected_citations[0].chunk_id == CHUNK_ID
        assert "SHA-256" in verdict.rejected_citations[0].reason

    def test_citacao_identica_e_verificada(self):
        verdict = review_citations(
            [_citation()], retrieved_chunk_ids=[CHUNK_ID], corpus_version=CORPUS_VERSION, passage_getter=_fake_getter()
        )
        assert len(verdict.verified_citations) == 1
        assert verdict.rejected_citations == []
        assert verdict.grounding_raw_ratio == 1.0


class TestChunkForaDosRecuperados:
    def test_chunk_id_fora_dos_recuperados_e_descartado_e_contado(self):
        verdict = review_citations(
            [_citation()],
            retrieved_chunk_ids=["outro-chunk-qualquer"],
            corpus_version=CORPUS_VERSION,
            passage_getter=_fake_getter(),
        )
        assert verdict.verified_citations == []
        assert len(verdict.rejected_citations) == 1
        assert verdict.rejected_citations[0].reason == "chunk_id fora dos chunks recuperados"
        assert verdict.grounding_raw_ratio == 0.0


class TestCOSExigeCitacaoVerificada:
    def _dossier_cos(self, citations: list[Citation]) -> Dossier:
        return Dossier(
            dossier_id=uuid4(),
            alert_id=uuid4(),
            type=DossierType.COS,
            summary="Resumo sintético do caso para fins de teste.",
            typology=Typology.STRUCTURING,
            cc4001_incisos=["I", "IV"],
            evidence=[],
            citations=citations,
            recommendation=Recommendation.COMUNICAR,
            ai_generated_fields=list(AiGeneratedField),
            deadlines=DossierDeadlines(selecao_em=NOW, prazo_interno=NOW, prazo_regulatorio_analise=NOW),
            versions=DossierVersions(rules=1, corpus="v1", mapping=2, features=1, prompt="p1", model="m1"),
            status=AlertState.DRAFT_READY,
        )

    def test_cos_sem_citacao_verificada_falha_e_vai_para_needs_human(self):
        verdict = review_citations(
            [_citation()],
            retrieved_chunk_ids=["outro-chunk-qualquer"],
            corpus_version=CORPUS_VERSION,
            passage_getter=_fake_getter(),
        )
        assert verdict.verified_citations == []
        with pytest.raises(ValidationError, match="NEEDS_HUMAN"):
            self._dossier_cos(verdict.verified_citations)

    def test_cos_com_citacao_verificada_monta_normalmente(self):
        verdict = review_citations(
            [_citation()], retrieved_chunk_ids=[CHUNK_ID], corpus_version=CORPUS_VERSION, passage_getter=_fake_getter()
        )
        dossier = self._dossier_cos(verdict.verified_citations)
        assert dossier.citations == verdict.verified_citations
