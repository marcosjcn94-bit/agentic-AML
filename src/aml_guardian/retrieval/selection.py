"""Seleção determinística de citações normativas (T1.8, RF-06, ADR-013 A): sem LLM.

Prioriza os `article_ref` preferenciais do mapeamento (SPEC.md §3.2); desempate por fusão de ranks (RRF) entre
a similaridade vetorial do MCP-03 e BM25 sobre o texto dos candidatos, recuperado via MCP-04. Trechos abaixo de
`selection.min_score` são descartados; no máximo `MAX_EVIDENCE` citações verificáveis (RF-06).
"""

from __future__ import annotations

import re
from typing import Protocol

from rank_bm25 import BM25Okapi

from aml_guardian.config.retrieval import RetrievalConfig, load_retrieval
from aml_guardian.contracts.pipeline import MAX_EVIDENCE, Citation, Typology
from aml_guardian.norms.server import get_norm_passage, search_norms
from aml_guardian.retrieval.query import NormSearcher, build_query, search_candidates
from aml_guardian.sourcedata.mapping import Tipologia

RRF_K = 60
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


class NormPassageGetter(Protocol):
    """Assinatura de MCP-04 `get_norm_passage` (injetável em teste)."""

    def __call__(self, chunk_id: str, corpus_version: str) -> dict[str, object]: ...


class NormPassageError(RuntimeError):
    """MCP-04 indisponível ou com resposta fora do formato esperado (RF-06)."""


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN_RE.findall(text)]


def _fetch_passage(chunk_id: str, corpus_version: str, getter: NormPassageGetter) -> dict[str, object]:
    resultado = getter(chunk_id=chunk_id, corpus_version=corpus_version)
    if not isinstance(resultado, dict) or resultado.get("status") != "success":
        raise NormPassageError(f"MCP-04 respondeu fora do formato esperado: {resultado!r}")
    return resultado


def _rank_by(candidatos: list[dict[str, object]], scores: dict[str, float]) -> dict[str, int]:
    """Ranking 1-indexado de `candidatos` por `scores` decrescente (insumo da fusão RRF)."""
    ordenados = sorted(candidatos, key=lambda c: scores[c["chunk_id"]], reverse=True)
    return {c["chunk_id"]: posicao + 1 for posicao, c in enumerate(ordenados)}


def select_citations(
    typology: Typology,
    enquadramento: Tipologia,
    corpus_version: str,
    searcher: NormSearcher = search_norms,
    passage_getter: NormPassageGetter = get_norm_passage,
    retrieval_cfg: RetrievalConfig | None = None,
) -> list[Citation]:
    """Seleciona no máximo `MAX_EVIDENCE` citações verificáveis, sem LLM (RF-06).

    Tipologia sem `applicability` curado no mapeamento (M4 ainda não chegou) não produz citação: `Citation`
    exige `applicability` não nulo (DT-09), então o alerta segue sem evidência normativa verificável.
    """
    if enquadramento.applicability is None:
        return []

    cfg = retrieval_cfg or load_retrieval()
    candidatos = search_candidates(typology, enquadramento, corpus_version, searcher)
    acima_do_limiar = [c for c in candidatos if c["score"] >= cfg.selection.min_score]
    if not acima_do_limiar:
        return []

    passagens = {c["chunk_id"]: _fetch_passage(c["chunk_id"], corpus_version, passage_getter) for c in acima_do_limiar}

    query = build_query(typology, enquadramento)
    corpus_tokens = [_tokenize(passagens[c["chunk_id"]]["text"]) for c in acima_do_limiar]
    bm25 = BM25Okapi(corpus_tokens)
    bm25_scores = dict(zip((c["chunk_id"] for c in acima_do_limiar), bm25.get_scores(_tokenize(query)), strict=True))

    vetor_scores = {c["chunk_id"]: c["score"] for c in acima_do_limiar}
    rank_vetorial = _rank_by(acima_do_limiar, vetor_scores)
    rank_bm25 = _rank_by(acima_do_limiar, bm25_scores)
    preferenciais = set(enquadramento.article_ref)

    def chave_ordenacao(c: dict[str, object]) -> tuple[bool, float]:
        rrf = 1 / (RRF_K + rank_vetorial[c["chunk_id"]]) + 1 / (RRF_K + rank_bm25[c["chunk_id"]])
        return (c["article_ref"] not in preferenciais, -rrf)  # preferencial primeiro; depois maior RRF

    selecionados = sorted(acima_do_limiar, key=chave_ordenacao)[:MAX_EVIDENCE]

    return [
        Citation(
            chunk_id=c["chunk_id"],
            article_ref=c["article_ref"],
            quoted_text=passagens[c["chunk_id"]]["text"],
            applicability=enquadramento.applicability,
        )
        for c in selecionados
    ]
