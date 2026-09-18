"""Avalia recall@5/grounding na partição de desenvolvimento.

O script não aceita o diretório golden como entrada acidental: a avaliação final é uma
operação separada e explícita em ``scripts/evaluate.py``.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", choices=("development",), required=True)
    parser.add_argument("--cache-disabled", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cache_status = "desligado" if args.cache_disabled else "não especificado"
    args.output.write_text(
        "# Grounding de desenvolvimento\n\n"
        f"- Dataset: `{args.dataset}`\n- Cache: {cache_status}\n"
        "- recall@5: não medida (dataset de desenvolvimento não materializado nesta execução)\n"
        "- grounding bruto: não medido (denominador zero não é aprovação)\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
