"""Contratos de ingestão e estado: DT-01 a DT-05 (SPEC.md §8.2, §9.1 API-01, RF-10).

DT-01 e DT-03 contêm dado pessoal e só existem em trânsito ou no `core_sintetico`.
DT-04 e DT-05 não admitem dado pessoal em claro: todo campo pessoal é um token `<TIPO>_<NN>`.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints, model_validator

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PiiToken = Annotated[str, StringConstraints(pattern=r"^[A-Z]+_\d{2,}$")]
CurrencyCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]


def _reject_inexact_number(value: object) -> object:
    """Recusa `float` e `bool` antes da conversão para evitar valor monetário binário impreciso."""
    if isinstance(value, bool | float):
        raise ValueError("amount_brl deve ser decimal exato (string, int ou Decimal)")
    return value


AmountBRL = Annotated[
    Decimal,
    BeforeValidator(_reject_inexact_number),
    Field(gt=0, decimal_places=2, allow_inf_nan=False),
]


class PaymentType(StrEnum):
    """Meio de pagamento da transação (DT-02)."""

    PIX = "PIX"
    TED = "TED"
    ESPECIE_DEPOSITO = "ESPECIE_DEPOSITO"
    ESPECIE_SAQUE = "ESPECIE_SAQUE"
    CARTAO = "CARTAO"
    TRANSFERENCIA_INTERNACIONAL = "TRANSFERENCIA_INTERNACIONAL"


class AlertState(StrEnum):
    """Estados da máquina de estados do alerta (RF-10)."""

    RECEIVED = "RECEIVED"
    SANITIZED = "SANITIZED"
    TRIAGED = "TRIAGED"
    INVESTIGATING = "INVESTIGATING"
    RESEARCHING = "RESEARCHING"
    REVIEWING = "REVIEWING"
    DRAFT_READY = "DRAFT_READY"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    RETURNED = "RETURNED"
    NEEDS_HUMAN = "NEEDS_HUMAN"


class TriageLevel(StrEnum):
    """Nível atribuído pela triagem determinística (RF-03)."""

    PROPOR_ARQUIVAMENTO = "PROPOR_ARQUIVAMENTO"
    INVESTIGAR = "INVESTIGAR"


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OccurrenceWindow(_Contract):
    """Janela de ocorrência das transações do alerta (DT-01)."""

    start: AwareDatetime
    end: AwareDatetime

    @model_validator(mode="after")
    def _start_not_after_end(self) -> Self:
        if self.start > self.end:
            raise ValueError("occurrence_window.start posterior a occurrence_window.end")
        return self


class _TransactionBase(_Contract):
    transaction_id: NonEmptyStr
    timestamp: AwareDatetime
    amount_brl: AmountBRL
    payment_type: PaymentType
    sender_location: NonEmptyStr
    receiver_location: NonEmptyStr
    currency_sent: CurrencyCode
    currency_received: CurrencyCode


class Transaction(_TransactionBase):
    """DT-02 — transação do alerta; contas são dado pessoal."""

    sender_account: NonEmptyStr
    receiver_account: NonEmptyStr


class SanitizedTransaction(_TransactionBase):
    """Transação do DT-04 com contas substituídas por token."""

    sender_account: PiiToken
    receiver_account: PiiToken


class SenderCustomer(_Contract):
    """Cliente remetente do DT-01 (dado pessoal)."""

    name: NonEmptyStr
    cpf_cnpj: NonEmptyStr


class SanitizedCustomer(_Contract):
    """Cliente remetente do DT-04 (somente tokens)."""

    name: PiiToken
    cpf_cnpj: PiiToken


class _AlertBase(_Contract):
    alert_id: UUID
    source_rule_id: NonEmptyStr
    selected_at: AwareDatetime
    occurrence_window: OccurrenceWindow


class Alert(_AlertBase):
    """DT-01 — alerta de entrada (API-01); contém dado pessoal, só em trânsito (RF-01)."""

    sender_account: NonEmptyStr
    sender_customer: SenderCustomer
    transactions: list[Transaction] = Field(min_length=1)


class SanitizedAlert(_AlertBase):
    """DT-04 — mesmos campos do DT-01 com tokens, mais `pii_token_count` e `sanitizer_version` (RF-02)."""

    sender_account: PiiToken
    sender_customer: SanitizedCustomer
    transactions: list[SanitizedTransaction] = Field(min_length=1)
    pii_token_count: int = Field(ge=0)
    sanitizer_version: NonEmptyStr


class SyntheticCustomer(_Contract):
    """DT-03 — cliente sintético do `core_sintetico` (dado pessoal sintético)."""

    customer_id: NonEmptyStr
    name: NonEmptyStr
    cpf_cnpj: NonEmptyStr
    accounts: list[NonEmptyStr] = Field(min_length=1)
    segment: NonEmptyStr
    restriction_flags: list[NonEmptyStr]


class AlertRecord(_Contract):
    """DT-05 — registro de estado e prazos do alerta, sem dado pessoal (RF-09, RF-10)."""

    alert_id: UUID
    state: AlertState
    triage_level: TriageLevel | None = None
    selected_at: AwareDatetime
    prazo_interno: AwareDatetime | None = None
    prazo_regulatorio_analise: AwareDatetime | None = None
    failure_reason: NonEmptyStr | None = None
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @model_validator(mode="after")
    def _needs_human_has_reason(self) -> Self:
        if self.state is AlertState.NEEDS_HUMAN and self.failure_reason is None:
            raise ValueError("NEEDS_HUMAN exige failure_reason (RF-10)")
        return self

    @model_validator(mode="after")
    def _triage_level_matches_state(self) -> Self:
        """Coerência com o diagrama do RF-10; `NEEDS_HUMAN` pode ocorrer antes ou depois da triagem."""
        if self.state in _PRE_TRIAGE_STATES and self.triage_level is not None:
            raise ValueError(f"{self.state} não admite triage_level (RF-10)")
        if self.state in _INVESTIGATION_STATES and self.triage_level is not TriageLevel.INVESTIGAR:
            raise ValueError(f"{self.state} exige triage_level INVESTIGAR (RF-10)")
        if self.state in _POST_TRIAGE_STATES and self.triage_level is None:
            raise ValueError(f"{self.state} exige triage_level (RF-10)")
        return self


_PRE_TRIAGE_STATES = frozenset({AlertState.RECEIVED, AlertState.SANITIZED})
_INVESTIGATION_STATES = frozenset({AlertState.INVESTIGATING, AlertState.RESEARCHING, AlertState.REVIEWING})
_POST_TRIAGE_STATES = frozenset(
    {AlertState.TRIAGED, AlertState.DRAFT_READY, AlertState.SUBMITTED, AlertState.APPROVED, AlertState.RETURNED}
)
