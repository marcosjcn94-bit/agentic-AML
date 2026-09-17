"""Download dos textos-fonte do corpus normativo (RF-14): Circular BCB 3.978/2020 e Carta Circular BCB 4.001/2020.

As URLs de metadado do `SPEC.md` §3.1/§3.2 devolvem só o cadastro do normativo (sem o texto); o PDF consolidado
mais recente fica hospedado em `normativos.bcb.gov.br`, resolvido aqui a partir do `Id` do normativo. Usa só a
biblioteca padrão (`urllib`) para não introduzir dependência de rede nova além do necessário (SPEC.md §6).

Fora do escopo funcional do T1.7 (lote3-brief.md): existe para materializar `data/raw/normas/` quando o
download ainda não rodou, chamado por `scripts/download/normas.py`.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from aml_guardian.norms.manifest import NormDocSource, sha256_of_file

_TIMEOUT_SECONDS = 30
_USER_AGENT = "aml-guardian-poc/0.1 (+RF-14 ingestao de corpus normativo)"
_PDF_HOST = "https://normativos.bcb.gov.br/Lists/Normativos/Attachments"


@dataclass(frozen=True)
class NormSource:
    """Um normativo a baixar: `doc_id` curto para `article_ref`, URL de metadado e nome do PDF consolidado."""

    doc_id: str
    metadata_url: str
    pdf_filename: str


# SPEC.md §3.1/§3.2: Circular BCB 3.978/2020 (política PLD-FT) e Carta Circular BCB 4.001/2020 (tipologias).
NORM_SOURCES = [
    NormSource(
        doc_id="Circ3978",
        metadata_url="https://www.bcb.gov.br/api/conteudo/app/normativos/exibenormativo?p1=Circular&p2=3978",
        pdf_filename="Circ_3978_v5_P.pdf",
    ),
    NormSource(
        doc_id="CC4001",
        metadata_url="https://www.bcb.gov.br/api/conteudo/app/normativos/exibenormativo?p1=Carta%20Circular&p2=4001",
        pdf_filename="C_Circ_4001_v4_P.pdf",
    ),
]


def _fetch(url: str) -> bytes:
    if not url.startswith("https://"):
        raise ValueError(f"URL de normativo deve ser https: {url!r}")
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310 - host fixo do BCB
        return response.read()


def _resolve_normativo_id(metadata_url: str) -> int:
    """Lê o cadastro do normativo (`SPEC.md` §3.1/§3.2) e devolve o `Id` interno usado no caminho do PDF."""
    payload = json.loads(_fetch(metadata_url).decode("utf-8"))
    conteudo = payload["conteudo"][0]
    return int(conteudo["Id"])


def download_norm_source(source: NormSource, dest_dir: Path) -> NormDocSource:
    """Baixa o PDF consolidado de `source` para `dest_dir` e devolve a entrada de manifesto (RF-14)."""
    normativo_id = _resolve_normativo_id(source.metadata_url)
    pdf_url = f"{_PDF_HOST}/{normativo_id}/{source.pdf_filename}"
    content = _fetch(pdf_url)

    dest_dir.mkdir(parents=True, exist_ok=True)
    local_path = dest_dir / f"{source.doc_id}.pdf"
    local_path.write_bytes(content)

    return NormDocSource(
        doc_id=source.doc_id,
        source_url=pdf_url,
        downloaded_at=datetime.now(UTC),
        doc_sha256=sha256_of_file(local_path),
        local_filename=local_path.name,
    )


def download_all(dest_dir: Path, sources: list[NormSource] | None = None) -> list[NormDocSource]:
    """Baixa todos os normativos de `sources` (padrão: `NORM_SOURCES`) para `dest_dir`."""
    return [download_norm_source(source, dest_dir) for source in (sources or NORM_SOURCES)]
