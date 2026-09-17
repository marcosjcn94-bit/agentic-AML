"""Extração de texto de PDF normativo via `pypdf` (T1.7, RF-14, ADR-015).

Isola a dependência de PDF em um único módulo; o parsing de dispositivo fica em `chunker.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pypdf

# Cabeçalho/rodapé repetido em cada página do BCB (ex.: "Circular nº 3.978, de 23 de janeiro de 2020 Página 3 de
# 25"); removido antes do chunking para não contaminar o texto de um dispositivo com paginação.
_RUNNING_HEADER_RE = re.compile(
    r"(Circular|Carta Circular)\s+n[ºo°]\s*[\d.]+,\s*de\s+\d{1,2}\s+de\s+\w+\s+de\s+\d{4}"
    r"\s+P[áa]gina\s+\d+\s+de\s+\d+"
)


def extract_pdf_text(path: Path) -> str:
    """Extrai o texto de todas as páginas de `path`, com o rodapé de paginação do BCB removido."""
    reader = pypdf.PdfReader(str(path))
    raw = "\n".join(page.extract_text() or "" for page in reader.pages)
    return _RUNNING_HEADER_RE.sub(" ", raw)
