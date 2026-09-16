"""PostToolUse hook: formata e corrige com ruff o arquivo .py recém-editado.

Recebe o payload JSON do Claude Code via stdin. Nunca bloqueia a edição:
violações que o ruff não corrige sozinho voltam ao modelo como contexto curto.
F401/F841 não são auto-corrigidos para não apagar um import/variável que a
próxima edição ainda vai usar.
"""

import json
import subprocess
import sys
from pathlib import Path

RUFF = Path(sys.executable).with_name("ruff.exe" if sys.platform == "win32" else "ruff")


def _ruff(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(RUFF), *args], capture_output=True, text=True, check=False)


def main() -> int:
    payload = json.load(sys.stdin)
    file_path = (payload.get("tool_input") or {}).get("file_path") or ""
    target = Path(file_path)
    if target.suffix != ".py" or not target.is_file() or not RUFF.is_file():
        return 0

    path = str(target)
    # fix antes de format: correções podem deixar o arquivo fora do padrão de formatação.
    result = _ruff(
        "check", "--fix", "--unfixable", "F401,F841", "--force-exclude", "--output-format", "concise", "--quiet", path
    )
    _ruff("format", "--quiet", "--force-exclude", path)
    remaining = result.stdout.strip().replace(path, target.name)
    if result.returncode != 0 and remaining:
        print(
            json.dumps(
                {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": f"ruff:\n{remaining}"}}
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
