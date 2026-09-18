"""Corpus normativo (T1.7): download, chunking, store ChromaDB e servidores MCP-03/MCP-04 (RF-14, SPEC.md §9.2)."""

from aml_guardian.norms.chunker import chunk_articles
from aml_guardian.norms.ingest import IngestResult, ingest_corpus
from aml_guardian.norms.server import get_norm_passage, search_norms
from aml_guardian.norms.store import NormsStore

__all__ = ["IngestResult", "NormsStore", "chunk_articles", "get_norm_passage", "ingest_corpus", "search_norms"]
