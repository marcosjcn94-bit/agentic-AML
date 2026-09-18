"""Manifesto de download do corpus normativo: `source_url`, `downloaded_at`, `doc_sha256` por documento (RF-14).

`corpus_version` deriva do conjunto de `doc_sha256`: mudar qualquer PDF de origem muda a versão; reingerir sem
mudança nenhuma mantém a mesma versão (RF-14, invalidação do cache semântico do RF-04).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import AwareDatetime, BaseModel, ConfigDict, HttpUrl

MANIFEST_FILENAME = "manifest.json"


class NormDocSource(BaseModel):
    """Um documento baixado do manifesto (RF-14); `doc_id` curto é usado no `article_ref` (ex.: `Circ3978`)."""

    model_config = ConfigDict(extra="forbid")

    doc_id: str
    source_url: HttpUrl
    downloaded_at: AwareDatetime
    doc_sha256: str
    local_filename: str


class NormsManifest(BaseModel):
    """Conteúdo de `data/raw/normas/manifest.json`."""

    model_config = ConfigDict(extra="forbid")

    documents: list[NormDocSource]


def sha256_of_file(path: Path) -> str:
    """SHA-256 hexadecimal do conteúdo binário do arquivo."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def derive_corpus_version(documents: list[NormDocSource]) -> str:
    """`corpus_version` = SHA-256 dos `doc_sha256` ordenados por `doc_id` (reingestão sem mudança mantém, RF-14)."""
    ordered = sorted(documents, key=lambda doc: doc.doc_id)
    joined = "|".join(f"{doc.doc_id}:{doc.doc_sha256}" for doc in ordered)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def write_manifest(path: Path, documents: list[NormDocSource]) -> None:
    """Grava o manifesto como JSON legível."""
    manifest = NormsManifest(documents=documents)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")


def load_manifest(path: Path) -> NormsManifest:
    """Lê o manifesto gravado por `write_manifest`."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    return NormsManifest.model_validate(raw)
