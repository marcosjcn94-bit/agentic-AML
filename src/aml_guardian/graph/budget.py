"""Orçamento de tempo e tokens por alerta (RF-10)."""

from __future__ import annotations

from datetime import UTC, datetime

from aml_guardian.contracts.runtime import Budget, InvestigationState


class BudgetExceededError(RuntimeError):
    """Alerta excedeu o orçamento operacional."""


class BudgetTracker:
    max_tokens = 2_000
    max_seconds = 40.0

    @classmethod
    def consume_tokens(cls, state: InvestigationState, tokens_in: int, tokens_out: int) -> InvestigationState:
        if tokens_in < 0 or tokens_out < 0:
            raise ValueError("tokens não podem ser negativos")
        used = state.budget.tokens_used + tokens_in + tokens_out
        updated = state.model_copy(update={"budget": Budget(tokens_used=used, started_at=state.budget.started_at)})
        if used > cls.max_tokens:
            raise BudgetExceededError(f"budget de tokens excedido: {used}/{cls.max_tokens}")
        return updated

    @classmethod
    def ensure_time(cls, state: InvestigationState, now: datetime | None = None) -> None:
        current = now or datetime.now(UTC)
        elapsed = (current - state.budget.started_at).total_seconds()
        if elapsed > cls.max_seconds:
            raise BudgetExceededError(f"budget de tempo excedido: {elapsed:.3f}/{cls.max_seconds}s")
