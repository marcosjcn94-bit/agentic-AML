"""Políticas comuns de execução dos nós do grafo (RF-10/RNF-06)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic, sleep
from typing import TypeVar


class NodeExecutionError(RuntimeError):
    """Falha controlada de execução, com indicação de possibilidade de retry."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class NodeTimeoutError(NodeExecutionError):
    """A operação ultrapassou o orçamento do nó."""


@dataclass(frozen=True)
class NodePolicy:
    timeout_seconds: float
    max_retries: int = 2
    backoff_seconds: tuple[float, float] = (0.1, 0.2)

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0 or self.max_retries < 0:
            raise ValueError("policy deve ter timeout positivo e retries não negativos")


T = TypeVar("T")


def execute_with_retry(
    operation: Callable[[], T],
    policy: NodePolicy,
    *,
    clock: Callable[[], float] = monotonic,
    sleeper: Callable[[float], None] = sleep,
) -> T:
    """Executa operação com timeout cooperativo e no máximo ``max_retries`` retries."""
    last: Exception | None = None
    for attempt in range(policy.max_retries + 1):
        started = clock()
        try:
            result = operation()
            elapsed = clock() - started
            if elapsed > policy.timeout_seconds:
                raise NodeTimeoutError(f"timeout após {elapsed:.3f}s", retryable=True)
            return result
        except NodeExecutionError as exc:
            last = exc
            if not exc.retryable or attempt == policy.max_retries:
                raise
        except Exception as exc:  # noqa: BLE001 - falhas externas são não retryable por padrão
            last = exc
            raise
        delay = policy.backoff_seconds[min(attempt, len(policy.backoff_seconds) - 1)]
        sleeper(delay)
    raise NodeExecutionError(str(last or "execução sem resultado"))


NODE_POLICIES: dict[str, NodePolicy] = {
    "triage": NodePolicy(3.0),
    "investigation": NodePolicy(28.0),
    "retrieval": NodePolicy(1.0),
    "selection": NodePolicy(1.0),
    "reviewer": NodePolicy(2.0),
    "dossier": NodePolicy(2.0),
}
