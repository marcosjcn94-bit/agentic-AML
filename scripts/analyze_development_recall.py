"""Gera relatório mecânico da partição de desenvolvimento, sem executar golden."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(
        "# Recall de desenvolvimento\n\n"
        "A partição de desenvolvimento deve ser fornecida pelo pipeline de sourcedata. "
        "Este relatório não executa nem lê `data/golden`.\n\n"
        "Status: não medida nesta execução isolada.\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
