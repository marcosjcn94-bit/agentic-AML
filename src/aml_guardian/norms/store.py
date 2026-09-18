"""Coleção ChromaDB `norms` para busca vetorial (MCP-03) e recuperação por id (MCP-04) — T1.7, RF-14, ADR-009.

Embedding: `paraphrase-multilingual-MiniLM-L12-v2` via FastEmbed (`SPEC.md` §6), definitivo desde o M4 (ADR-016) —
mantido o candidato da ADR-009 pelo critério de menor custo de token/tempo, sem nova rodada de recall@5.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from aml_guardian.contracts.pipeline import NormChunk

DEFAULT_PERSIST_DIR = Path(__file__).resolve().parents[3] / "data" / "chroma"
COLLECTION_NAME = "norms"
EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"  # candidato provisório (ADR-009); M4 decide em definitivo


class Embedder(Protocol):
    """Assinatura mínima usada pela store (injetável em teste; produção usa FastEmbed)."""

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FastEmbedEmbedder:
    """Embedder de produção: `fastembed.TextEmbedding` carregado sob demanda (evita custo/rede no import)."""

    def __init__(self, model_name: str = EMBEDDING_MODEL):
        self._model_name = model_name
        self._model = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self._model_name)
        return [vector.tolist() for vector in self._model.embed(texts)]


class NormsStore:
    """Wrapper fino sobre a coleção ChromaDB `norms`: upsert por chunk e busca/recuperação por `corpus_version`."""

    def __init__(self, persist_dir: Path | None = None, embedder: Embedder | None = None):
        import chromadb

        self._client = chromadb.PersistentClient(path=str(persist_dir or DEFAULT_PERSIST_DIR))
        self._collection = self._client.get_or_create_collection(COLLECTION_NAME)
        self._embedder = embedder or FastEmbedEmbedder()

    def upsert_chunks(self, chunks: list[NormChunk]) -> None:
        """Insere/atualiza os chunks; embedding calculado sobre o texto preservado (não normalizado)."""
        if not chunks:
            return
        vectors = self._embedder.embed([chunk.text for chunk in chunks])
        self._collection.upsert(
            ids=[chunk.chunk_id for chunk in chunks],
            embeddings=vectors,
            documents=[chunk.text for chunk in chunks],
            metadatas=[
                {
                    "doc_id": chunk.doc_id,
                    "article_ref": chunk.article_ref,
                    "text_sha256": chunk.text_sha256,
                    "corpus_version": chunk.corpus_version,
                    "source_url": str(chunk.source_url),
                }
                for chunk in chunks
            ],
        )

    def search(self, query: str, top_k: int, corpus_version: str) -> list[dict[str, object]]:
        """Busca vetorial restrita a `corpus_version`; devolve só `chunk_id`, `article_ref` e `score` (MCP-03)."""
        vector = self._embedder.embed([query])[0]
        result = self._collection.query(
            query_embeddings=[vector], n_results=top_k, where={"corpus_version": corpus_version}
        )
        ids = result.get("ids", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        return [
            {"chunk_id": chunk_id, "article_ref": metadata["article_ref"], "score": 1.0 - distance}
            for chunk_id, metadata, distance in zip(ids, metadatas, distances, strict=True)
        ]

    def get_chunk(self, chunk_id: str, corpus_version: str) -> NormChunk | None:
        """Recupera um chunk por id, só se pertencer a `corpus_version` (MCP-04; 404 lógico caso contrário)."""
        result = self._collection.get(ids=[chunk_id], include=["documents", "metadatas"])
        ids = result.get("ids", [])
        if not ids:
            return None
        metadata = result["metadatas"][0]
        if metadata["corpus_version"] != corpus_version:
            return None
        return NormChunk(
            chunk_id=chunk_id,
            doc_id=metadata["doc_id"],
            article_ref=metadata["article_ref"],
            text=result["documents"][0],
            text_sha256=metadata["text_sha256"],
            corpus_version=metadata["corpus_version"],
            source_url=metadata["source_url"],
        )
