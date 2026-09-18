"""Chunking do corpus normativo por dispositivo (artigo/parágrafo/inciso/alínea) — T1.7, RF-14.

Produz `article_ref` estruturado (ex.: `Circ3978/art43/p1`, `CC4001/art1/i1/d`) e os `NormChunk` (DT-08)
correspondentes: `text` preservado como extraído da fonte (sem normalização; RF-06 exige cópia literal via
MCP-04) e `text_sha256` do trecho normalizado (`aml_guardian.norms.normalize`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from aml_guardian.contracts.pipeline import NormChunk
from aml_guardian.norms.normalize import text_sha256

_ARTICLE_RE = re.compile(r"(?m)^[ \t]*Art\.\s*(\d+)[º°]?\.?[ \t]+")
_PARAGRAPH_RE = re.compile(r"(?m)^[ \t]*§\s*(\d+)[º°][ \t]+")
_SOLE_PARAGRAPH_RE = re.compile(r"(?m)^[ \t]*Par[aá]grafo\s+[uú]nico\.[ \t]+")
_INCISO_RE = re.compile(r"(?m)^[ \t]*([IVXLCDM]+)\s*-\s+")
_ALINEA_RE = re.compile(r"(?m)^[ \t]*([a-z])\)[ \t]+")

_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def _roman_to_int(roman: str) -> int:
    total, previous = 0, 0
    for char in reversed(roman):
        value = _ROMAN_VALUES[char]
        total += -value if value < previous else value
        previous = max(previous, value)
    return total


@dataclass(frozen=True)
class _Segment:
    marker: str | None
    body: str


def _split(text: str, marker_re: re.Pattern[str], *, sole: bool = False) -> list[_Segment]:
    """Divide `text` nas ocorrências de `marker_re`; o trecho antes da 1ª ocorrência fica sem marcador."""
    matches = list(marker_re.finditer(text))
    if not matches:
        return [_Segment(marker=None, body=text)]
    segments = []
    intro = text[: matches[0].start()]
    if intro.strip():
        segments.append(_Segment(marker=None, body=intro))
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        marker = "u" if sole else match.group(1)
        segments.append(_Segment(marker=marker, body=text[start:end]))
    return segments


def _leaf(chunks: list[NormChunk], doc_id: str, source_url: str, corpus_version: str, ref: str, body: str) -> None:
    stripped = body.strip()
    if not stripped:
        return
    chunks.append(
        NormChunk(
            chunk_id=f"{doc_id}:{ref}:{corpus_version}",
            doc_id=doc_id,
            article_ref=ref,
            text=stripped,
            text_sha256=text_sha256(stripped),
            corpus_version=corpus_version,
            source_url=source_url,
        )
    )


def _chunk_alineas(chunks: list[NormChunk], doc_id: str, source_url: str, corpus_version: str, ref: str, body: str):
    segments = _split(body, _ALINEA_RE)
    if len(segments) == 1 and segments[0].marker is None:
        _leaf(chunks, doc_id, source_url, corpus_version, ref, body)
        return
    for segment in segments:
        leaf_ref = ref if segment.marker is None else f"{ref}/{segment.marker}"
        _leaf(chunks, doc_id, source_url, corpus_version, leaf_ref, segment.body)


def _chunk_incisos(chunks: list[NormChunk], doc_id: str, source_url: str, corpus_version: str, ref: str, body: str):
    segments = _split(body, _INCISO_RE)
    if len(segments) == 1 and segments[0].marker is None:
        _leaf(chunks, doc_id, source_url, corpus_version, ref, body)
        return
    for segment in segments:
        if segment.marker is None:
            _leaf(chunks, doc_id, source_url, corpus_version, f"{ref}/caput", segment.body)
            continue
        inciso_ref = f"{ref}/i{_roman_to_int(segment.marker)}"
        _chunk_alineas(chunks, doc_id, source_url, corpus_version, inciso_ref, segment.body)


def _chunk_paragraphs(chunks: list[NormChunk], doc_id: str, source_url: str, corpus_version: str, ref: str, body: str):
    numbered = _split(body, _PARAGRAPH_RE)
    has_numbered = any(segment.marker is not None for segment in numbered)
    if not has_numbered:
        sole = _split(body, _SOLE_PARAGRAPH_RE, sole=True)
        has_sole = any(segment.marker is not None for segment in sole)
        segments = sole if has_sole else None
    else:
        segments = numbered
    if segments is None:
        _chunk_incisos(chunks, doc_id, source_url, corpus_version, ref, body)
        return
    for segment in segments:
        if segment.marker is None:
            _chunk_incisos(chunks, doc_id, source_url, corpus_version, f"{ref}/caput", segment.body)
            continue
        paragraph_ref = f"{ref}/p{segment.marker}"
        _chunk_incisos(chunks, doc_id, source_url, corpus_version, paragraph_ref, segment.body)


def chunk_articles(doc_id: str, source_url: str, corpus_version: str, raw_text: str) -> list[NormChunk]:
    """Divide `raw_text` por artigo/parágrafo/inciso/alínea e devolve os `NormChunk` (DT-08) resultantes.

    Texto antes do primeiro `Art.` (preâmbulo, ementa) é descartado: não é dispositivo citável (RF-14).
    """
    articles = _split(raw_text, _ARTICLE_RE)
    chunks: list[NormChunk] = []
    for segment in articles:
        if segment.marker is None:
            continue
        ref = f"{doc_id}/art{segment.marker}"
        _chunk_paragraphs(chunks, doc_id, source_url, corpus_version, ref, segment.body)
    return chunks
