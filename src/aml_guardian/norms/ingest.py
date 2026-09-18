"""Orquestra a ingestão do corpus normativo (T1.7, RF-14): manifesto -> extração -> chunking -> store opcional.

`corpus_version` deriva do manifesto (`aml_guardian.norms.manifest.derive_corpus_version`); reingerir os mesmos
PDFs produz os mesmos `doc_sha256` e, portanto, a mesma versão ("reingestão sem mudança não altera
corpus_version", RF-14).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from aml_guardian.contracts.pipeline import NormChunk
from aml_guardian.norms.chunker import chunk_articles
from aml_guardian.norms.manifest import MANIFEST_FILENAME, derive_corpus_version, load_manifest
from aml_guardian.norms.pdf_extract import extract_pdf_text
from aml_guardian.norms.store import NormsStore

RAW_DIR = Path(__file__).resolve().parents[3] / "data" / "raw" / "normas"


class IngestResult(BaseModel):
    """Resultado da ingestão: versão do corpus e os chunks produzidos."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    corpus_version: str
    chunks: list[NormChunk]


def ingest_corpus(raw_dir: Path | None = None, store: NormsStore | None = None) -> IngestResult:
    """Lê o manifesto de `raw_dir`, extrai e faz o chunking de cada PDF; grava na `store` se fornecida."""
    directory = raw_dir or RAW_DIR
    manifest = load_manifest(directory / MANIFEST_FILENAME)
    corpus_version = derive_corpus_version(manifest.documents)

    chunks: list[NormChunk] = []
    for document in manifest.documents:
        raw_text = extract_pdf_text(directory / document.local_filename)
        chunks.extend(chunk_articles(document.doc_id, str(document.source_url), corpus_version, raw_text))

    if store is not None:
        store.upsert_chunks(chunks)

    return IngestResult(corpus_version=corpus_version, chunks=chunks)
