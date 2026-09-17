"""`GET /health` (T1.11, API-09): checagens injetáveis, mesmo padrão de `GraphDeps` (T1.10).

Cada dependência tem uma checagem padrão (sqlite real, coleção Chroma, ping no `api_base` do LiteLLM, manifesto
do corpus) e um `Callable` opcional que os testes substituem para simular indisponibilidade sem rede real.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx
from pydantic import BaseModel

from aml_guardian.norms.manifest import MANIFEST_FILENAME, derive_corpus_version, load_manifest
from aml_guardian.persistence.db import get_connection, get_db_path

RAW_NORMS_DIR = Path(__file__).resolve().parents[3] / "data" / "raw" / "normas"

SqliteChecker = Callable[[], bool]
ChromaChecker = Callable[[], bool]
OllamaChecker = Callable[[], bool]
CorpusVersionGetter = Callable[[], str | None]


class HealthResult(BaseModel):
    status: str
    ollama: bool
    chroma: bool
    sqlite: bool
    corpus_version: str | None


def _default_sqlite_checker(db_path: Path | None) -> SqliteChecker:
    def _check() -> bool:
        try:
            conn = get_connection(db_path or get_db_path())
            try:
                conn.execute("SELECT 1")
            finally:
                conn.close()
            return True
        except Exception:  # noqa: BLE001 - health check é fail-closed por natureza
            return False

    return _check


def _default_chroma_checker(persist_dir: Path | None) -> ChromaChecker:
    def _check() -> bool:
        try:
            import chromadb

            from aml_guardian.norms.store import DEFAULT_PERSIST_DIR

            client = chromadb.PersistentClient(path=str(persist_dir or DEFAULT_PERSIST_DIR))
            client.heartbeat()
            return True
        except Exception:  # noqa: BLE001
            return False

    return _check


def _default_ollama_checker(api_base: str | None) -> OllamaChecker:
    def _check() -> bool:
        if api_base is None:
            return False
        try:
            resp = httpx.get(api_base, timeout=2.0)
            return resp.status_code < 500
        except Exception:  # noqa: BLE001
            return False

    return _check


def _default_corpus_version_getter(manifest_path: Path | None) -> CorpusVersionGetter:
    def _get() -> str | None:
        try:
            manifest = load_manifest(manifest_path or (RAW_NORMS_DIR / MANIFEST_FILENAME))
            return derive_corpus_version(manifest.documents)
        except Exception:  # noqa: BLE001
            return None

    return _get


@dataclass
class HealthDeps:
    """Feixe de dependências do `/health`; todos os campos são opcionais, como `GraphDeps` (T1.10)."""

    sqlite_checker: SqliteChecker | None = None
    chroma_checker: ChromaChecker | None = None
    ollama_checker: OllamaChecker | None = None
    corpus_version_getter: CorpusVersionGetter | None = None
    db_path: Path | None = None
    chroma_dir: Path | None = None
    manifest_path: Path | None = None
    ollama_api_base: str | None = None


def check_health(deps: HealthDeps) -> HealthResult:
    sqlite_ok = (deps.sqlite_checker or _default_sqlite_checker(deps.db_path))()
    chroma_ok = (deps.chroma_checker or _default_chroma_checker(deps.chroma_dir))()
    ollama_ok = (deps.ollama_checker or _default_ollama_checker(deps.ollama_api_base))()
    corpus_version = (deps.corpus_version_getter or _default_corpus_version_getter(deps.manifest_path))()
    healthy = sqlite_ok and chroma_ok and ollama_ok and corpus_version is not None
    return HealthResult(
        status="ok" if healthy else "degraded",
        ollama=ollama_ok,
        chroma=chroma_ok,
        sqlite=sqlite_ok,
        corpus_version=corpus_version,
    )
