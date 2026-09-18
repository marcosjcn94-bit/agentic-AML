"""Executa verificações locais de segurança e gera evidência sem mascarar ferramentas ausentes."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    tools = ["bandit", "pip-audit", "semgrep", "zap-baseline.py"]
    lines = ["# Security scan", "", "| Ferramenta | Disponível |", "|---|---|"]
    missing = []
    for tool in tools:
        available = shutil.which(tool) is not None
        lines.append(f"| `{tool}` | {'sim' if available else 'não'} |")
        if not available:
            missing.append(tool)
    lines += ["", "Ferramentas ausentes não são consideradas aprovadas."]
    if missing:
        lines.append(f"Indisponíveis: {', '.join(missing)}")
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 2 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
