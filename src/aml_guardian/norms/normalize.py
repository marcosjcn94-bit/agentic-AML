"""Normalização de texto normativo para hash estável (T1.7, RF-14).

`text_sha256` do DT-08 é calculado sobre o trecho NORMALIZADO (NFC, espaços colapsados, trim); o campo `text`
do chunk preserva o trecho como extraído da fonte, sem normalização (RF-06 exige cópia literal via MCP-04).
O Revisor (T1.8, RF-07) repete esta mesma normalização para verificar a citação.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

_WHITESPACE_RUN = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """NFC + colapso de espaços (incluindo quebras de linha) + trim; usada só para o hash (RF-14)."""
    nfc = unicodedata.normalize("NFC", text)
    collapsed = _WHITESPACE_RUN.sub(" ", nfc)
    return collapsed.strip()


def text_sha256(text: str) -> str:
    """SHA-256 hexadecimal do texto já normalizado por `normalize_text`."""
    normalized = normalize_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
