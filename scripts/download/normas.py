"""CLI: baixa o corpus normativo (Circ. BCB 3.978/2020 e CC BCB 4.001/2020) para `data/raw/normas/` (RF-14).

Fora do escopo funcional do T1.7 (lote3-brief.md); existe só para materializar `data/raw/normas/manifest.json`
quando ausente, pré-requisito da ingestão em `aml_guardian.norms.ingest`. Uso: `python scripts/download/normas.py`.
"""

from __future__ import annotations

from pathlib import Path

from aml_guardian.norms.downloader import download_all
from aml_guardian.norms.manifest import MANIFEST_FILENAME, write_manifest

DEST_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "normas"


def main() -> None:
    documents = download_all(DEST_DIR)
    write_manifest(DEST_DIR / MANIFEST_FILENAME, documents)
    for doc in documents:
        print(f"{doc.doc_id}: {doc.local_filename} ({doc.doc_sha256[:12]}...)")


if __name__ == "__main__":
    main()
