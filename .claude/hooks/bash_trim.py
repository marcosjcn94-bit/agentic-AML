"""PreToolUse hook (matcher Bash): nega comandos que tendem a devolver saída
grande e sem filtro, antes de eles rodarem.

Um PostToolUse não serve para isso: o stdout de um Bash já executado chega
ao modelo antes do hook rodar, então só dá para *anexar* contexto (mais
tokens), nunca encolher o que já foi mostrado. Por isso este hook age em
PreToolUse e nega o comando, deixando o próprio modelo reescrevê-lo.

Cobre só os casos que a política do CLAUDE.md do projeto já proíbe
explicitamente (rodar a suite inteira em vez de `pytest -k`, usar `cat`/
`find` no lugar das ferramentas dedicadas Read/Glob) — evita falso positivo
em `git log`/`git diff` sem filtro, que o próprio fluxo de commit precisa
rodar sem restrição às vezes.
"""

import json
import re
import sys

_PIPE_FILTER = re.compile(r"\|\s*(head|tail|grep|wc|less|sed\s+-n)\b")
_CAT = re.compile(r"(^|[;&|]\s*)(cat|type)\s+\S")
_FIND = re.compile(r"(^|[;&|]\s*)find\s+")
_TEST_RUN = re.compile(r"\b(pytest|npm\s+test|go\s+test)\b")
_TEST_FILTER_FLAGS = ("-k", "-x", "-q", "--quiet")


def _deny(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


def main() -> int:
    payload = json.load(sys.stdin)
    command = ((payload.get("tool_input") or {}).get("command") or "").strip()
    if not command:
        return 0

    has_filter = bool(_PIPE_FILTER.search(command))

    if _CAT.search(command) and not has_filter:
        _deny("cat/type sem filtro: use a ferramenta Read, ou pipe para head/tail/grep.")
        return 0

    if _FIND.search(command) and "-maxdepth" not in command and "-name" not in command and "-iname" not in command:
        _deny("find sem -maxdepth/-name: use a ferramenta Glob, ou restrinja o find.")
        return 0

    if _TEST_RUN.search(command) and not has_filter and not any(f in command for f in _TEST_FILTER_FLAGS):
        _deny("suite inteira sem filtro: rode só o teste afetado (ex.: pytest -k <nome>).")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
