"""Cache semântico versionado de consultas normativas (RF-04)."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from aml_guardian.norms.store import DEFAULT_PERSIST_DIR, Embedder, FastEmbedEmbedder


class SemanticNormCache:
    """Coleção isolada do corpus, contendo somente metadados normativos mínimos."""

    collection_name = "semantic_cache"

    def __init__(
        self,
        persist_dir: Path | None = None,
        embedder: Embedder | None = None,
        threshold: float = 0.92,
        enabled: bool = True,
        collection: Any | None = None,
    ) -> None:
        if not 0 < threshold <= 1:
            raise ValueError("threshold deve estar entre 0 e 1")
        self.enabled = enabled
        self.threshold = threshold
        self._embedder = embedder or FastEmbedEmbedder()
        if collection is not None:
            self._collection = collection
        else:
            import chromadb

            client = chromadb.PersistentClient(path=str(persist_dir or DEFAULT_PERSIST_DIR))
            self._collection = client.get_or_create_collection(self.collection_name)

    def lookup(self, query: str, corpus_version: str) -> list[dict[str, object]] | None:
        if not self.enabled:
            return None
        vector = self._embedder.embed([query])[0]
        result = self._collection.query(query_embeddings=[vector], n_results=1)
        ids = result.get("ids", [[]])[0]
        distances = result.get("distances", [[]])[0]
        metadata = result.get("metadatas", [[]])[0]
        if not ids or not distances or not metadata or 1.0 - distances[0] < self.threshold:
            return None
        if metadata[0].get("corpus_version") != corpus_version:
            return None
        values = ast.literal_eval(str(metadata[0].get("candidates", "[]")))
        return [self._safe_candidate(value) for value in values if isinstance(value, dict)]

    def store(self, query: str, corpus_version: str, candidates: list[dict[str, object]]) -> None:
        if not self.enabled:
            return
        safe = [self._safe_candidate(candidate) for candidate in candidates]
        self._collection.upsert(
            ids=[f"{corpus_version}:{hash(query)}"],
            embeddings=[self._embedder.embed([query])[0]],
            documents=[query],
            metadatas=[{"corpus_version": corpus_version, "candidates": repr(safe)}],
        )

    @staticmethod
    def _safe_candidate(candidate: dict[str, object]) -> dict[str, object]:
        allowed = {"chunk_id", "article_ref", "score"}
        if not allowed.issuperset(candidate):
            raise ValueError("cache normativo recebeu metadado proibido")
        return {key: candidate[key] for key in allowed if key in candidate}
