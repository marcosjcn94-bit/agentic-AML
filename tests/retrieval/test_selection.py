"""Testes da Seleção determinística de citações (T1.8, RF-06): preferencial, min_score e teto de 3."""

from __future__ import annotations

from aml_guardian.contracts.pipeline import MAX_EVIDENCE, Typology
from aml_guardian.retrieval.selection import select_citations
from aml_guardian.sourcedata.mapping import Tipologia

CORPUS_VERSION = "v1"

ENQUADRAMENTO = Tipologia(
    typology=Typology.STRUCTURING,
    incisos=["I", "IV"],
    alineas=["d", "e", "k"],
    critica=True,
    article_ref=["CC4001/art1/i1/d"],  # único preferencial nestes testes
    applicability="Fragmentação de depósitos ou saques para dissimular o valor total da movimentação (art. 1º, I, d).",
)

_TEXTS = {
    "chunk-d": "Fragmentação de depósitos em espécie para dissimular o valor total da movimentação.",
    "chunk-e": "Fragmentação de saques em espécie para burlar limites regulatórios de reportes de operações.",
    "chunk-i4": "Movimentação de contas de depósito incompatível com o patrimônio ou a atividade do cliente.",
    "chunk-extra1": "Depósitos ou aportes em espécie com atipicidade em relação à atividade econômica do cliente.",
    "chunk-extra2": "Saques no período de cinco dias úteis em valores inferiores aos limites estabelecidos.",
}


def _fake_searcher(results: list[dict[str, object]]):
    def searcher(query: str, top_k: int, corpus_version: str) -> dict[str, object]:
        return {"status": "success", "results": results[:top_k]}

    return searcher


def _fake_getter(texts: dict[str, str] = _TEXTS):
    def getter(chunk_id: str, corpus_version: str) -> dict[str, object]:
        if chunk_id not in texts:
            return {"error": "NOT_FOUND", "message": "sem texto", "retryable": False}
        return {"status": "success", "chunk_id": chunk_id, "text": texts[chunk_id], "text_sha256": "x" * 64}

    return getter


class TestPreferencialVenceRRF:
    def test_preferencial_e_selecionado_mesmo_com_score_vetorial_menor(self):
        candidatos = [
            {"chunk_id": "chunk-d", "article_ref": "CC4001/art1/i1/d", "score": 0.40},  # preferencial, score baixo
            {"chunk_id": "chunk-e", "article_ref": "CC4001/art1/i1/e", "score": 0.95},  # não preferencial, score alto
        ]
        citations = select_citations(
            Typology.STRUCTURING,
            ENQUADRAMENTO,
            CORPUS_VERSION,
            searcher=_fake_searcher(candidatos),
            passage_getter=_fake_getter(),
        )
        assert citations[0].article_ref == "CC4001/art1/i1/d"


class TestMinScore:
    def test_abaixo_do_min_score_e_descartado(self):
        candidatos = [
            {"chunk_id": "chunk-d", "article_ref": "CC4001/art1/i1/d", "score": 0.40},
            {"chunk_id": "chunk-i4", "article_ref": "CC4001/art1/i4", "score": 0.10},  # abaixo de min_score (0.35)
        ]
        citations = select_citations(
            Typology.STRUCTURING,
            ENQUADRAMENTO,
            CORPUS_VERSION,
            searcher=_fake_searcher(candidatos),
            passage_getter=_fake_getter(),
        )
        refs = {c.article_ref for c in citations}
        assert "CC4001/art1/i4" not in refs
        assert "CC4001/art1/i1/d" in refs

    def test_todos_abaixo_do_min_score_devolve_lista_vazia(self):
        candidatos = [{"chunk_id": "chunk-i4", "article_ref": "CC4001/art1/i4", "score": 0.05}]
        citations = select_citations(
            Typology.STRUCTURING,
            ENQUADRAMENTO,
            CORPUS_VERSION,
            searcher=_fake_searcher(candidatos),
            passage_getter=_fake_getter(),
        )
        assert citations == []


class TestTetoDeTres:
    def test_nunca_mais_de_tres_citacoes(self):
        candidatos = [
            {"chunk_id": "chunk-d", "article_ref": "CC4001/art1/i1/d", "score": 0.90},
            {"chunk_id": "chunk-e", "article_ref": "CC4001/art1/i1/e", "score": 0.85},
            {"chunk_id": "chunk-i4", "article_ref": "CC4001/art1/i4", "score": 0.80},
            {"chunk_id": "chunk-extra1", "article_ref": "CC4001/art1/i1/a", "score": 0.75},
            {"chunk_id": "chunk-extra2", "article_ref": "CC4001/art1/i1/k", "score": 0.70},
        ]
        citations = select_citations(
            Typology.STRUCTURING,
            ENQUADRAMENTO,
            CORPUS_VERSION,
            searcher=_fake_searcher(candidatos),
            passage_getter=_fake_getter(),
        )
        assert len(citations) == MAX_EVIDENCE == 3


class TestSemApplicabilityCurado:
    def test_tipologia_sem_applicability_nao_produz_citacao(self):
        sem_curadoria = ENQUADRAMENTO.model_copy(update={"applicability": None, "article_ref": []})
        candidatos = [{"chunk_id": "chunk-d", "article_ref": "CC4001/art1/i1/d", "score": 0.90}]
        citations = select_citations(
            Typology.STRUCTURING,
            sem_curadoria,
            CORPUS_VERSION,
            searcher=_fake_searcher(candidatos),
            passage_getter=_fake_getter(),
        )
        assert citations == []
