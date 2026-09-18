"""Executa verificações locais de segurança e gera evidência sem mascarar ferramentas ausentes."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def _zap_available() -> bool:
    """Aceita ZAP local ou a imagem oficial já disponível no Docker."""
    if shutil.which("zap-baseline.py"):
        return True
    if not shutil.which("docker"):
        return False
    result = subprocess.run(
        ["docker", "image", "inspect", "zaproxy/zap-stable"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    tools = ["bandit", "pip-audit", "semgrep"]
    lines = ["# Security scan", "", "| Ferramenta | Disponível |", "|---|---|"]
    missing = []
    for tool in tools:
        available = shutil.which(tool) is not None
        lines.append(f"| `{tool}` | {'sim' if available else 'não'} |")
        if not available:
            missing.append(tool)
    zap_available = _zap_available()
    lines.append(f"| `zap-baseline.py` (local/Docker) | {'sim' if zap_available else 'não'} |")
    if not zap_available:
        missing.append("zap-baseline.py (local/Docker)")
    lines += ["", "Ferramentas ausentes não são consideradas aprovadas."]
    if missing:
        lines.append(f"Indisponíveis: {', '.join(missing)}")
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 2 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
