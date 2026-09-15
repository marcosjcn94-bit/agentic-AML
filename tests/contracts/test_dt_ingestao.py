"""Contratos de ingestão (DT-01 a DT-04; SPEC.md §8.2, §9.1 API-01; T0.2). DT-05 em test_dt_ingestao_estado.py.

Dados sintéticos. Documento de identificação versionado só como token (`CPF_01`); valores
em formato de documento são gerados em tempo de execução.
"""

from __future__ import annotations

import copy
import random
from decimal import Decimal
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from aml_guardian.contracts.ingestion import (
    Alert,
    AlertRecord,
    PaymentType,
    SanitizedAlert,
    SyntheticCustomer,
    Transaction,
)

API01_EXAMPLE: dict[str, Any] = {
    "alert_id": "8f5c2a1e-3b7d-4c9a-9e21-6a0f4d2b7c11",
    "source_rule_id": "LEG-ESPECIE-FRAG-01",
    "selected_at": "2026-09-15T13:00:00Z",
    "sender_account": "0001-0012345-6",
    "sender_customer": {"name": "Cliente Sintético Um", "cpf_cnpj": "CPF_01"},
    "occurrence_window": {"start": "2026-09-08T00:00:00Z", "end": "2026-09-14T23:59:59Z"},
    "transactions": [
        {
            "transaction_id": "tx-0001",
            "timestamp": "2026-09-09T10:12:00Z",
            "amount_brl": "9800.00",
            "payment_type": "ESPECIE_DEPOSITO",
            "sender_account": "0001-0012345-6",
            "receiver_account": "0001-0012345-6",
            "sender_location": "BR",
            "receiver_location": "BR",
            "currency_sent": "BRL",
            "currency_received": "BRL",
        }
    ],
}


def _api01() -> dict[str, Any]:
    return copy.deepcopy(API01_EXAMPLE)


def _sanitized() -> dict[str, Any]:
    payload = _api01()
    payload["sender_account"] = "CONTA_01"
    payload["sender_customer"] = {"name": "NOME_01", "cpf_cnpj": "CPF_01"}
    payload["transactions"][0]["sender_account"] = "CONTA_01"
    payload["transactions"][0]["receiver_account"] = "CONTA_01"
    payload["pii_token_count"] = 3
    payload["sanitizer_version"] = "0.1.0"
    return payload


def _runtime_cpf_like() -> str:
    rng = random.Random(2026)
    digits = "".join(str(rng.randint(0, 9)) for _ in range(11))
    return f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}"


# DT-01 / DT-02 ---------------------------------------------------------------


def test_dt_ingestao_payload_api01_valido() -> None:
    alert = Alert.model_validate(_api01())
    tx = alert.transactions[0]
    assert str(alert.alert_id) == API01_EXAMPLE["alert_id"]
    assert tx.amount_brl == Decimal("9800.00")
    assert tx.payment_type is PaymentType.ESPECIE_DEPOSITO
    assert alert.selected_at.utcoffset() is not None


@pytest.mark.parametrize(
    "field",
    [
        "alert_id",
        "source_rule_id",
        "selected_at",
        "sender_account",
        "sender_customer",
        "transactions",
        "occurrence_window",
    ],
)
def test_dt_ingestao_alerta_sem_campo_obrigatorio(field: str) -> None:
    payload = _api01()
    del payload[field]
    with pytest.raises(ValidationError):
        Alert.model_validate(payload)


@pytest.mark.parametrize(
    "field",
    [
        "transaction_id",
        "timestamp",
        "amount_brl",
        "payment_type",
        "sender_account",
        "receiver_account",
        "sender_location",
        "receiver_location",
        "currency_sent",
        "currency_received",
    ],
)
def test_dt_ingestao_transacao_sem_campo_obrigatorio(field: str) -> None:
    payload = _api01()
    del payload["transactions"][0][field]
    with pytest.raises(ValidationError):
        Alert.model_validate(payload)


def test_dt_ingestao_payment_type_desconhecido() -> None:
    payload = _api01()
    payload["transactions"][0]["payment_type"] = "BOLETO"
    with pytest.raises(ValidationError):
        Alert.model_validate(payload)


def test_dt_ingestao_payment_type_enum_do_spec() -> None:
    assert {p.value for p in PaymentType} == {
        "PIX",
        "TED",
        "ESPECIE_DEPOSITO",
        "ESPECIE_SAQUE",
        "CARTAO",
        "TRANSFERENCIA_INTERNACIONAL",
    }


@pytest.mark.parametrize("amount", ["abc", "", 9800.5, True, "9800.001", "0", "-10.00", "NaN", "Infinity"])
def test_dt_ingestao_amount_brl_nao_decimal(amount: object) -> None:
    payload = _api01()
    payload["transactions"][0]["amount_brl"] = amount
    with pytest.raises(ValidationError):
        Alert.model_validate(payload)


@pytest.mark.parametrize("amount", ["9800", "0.01", 9800, Decimal("12.5")])
def test_dt_ingestao_amount_brl_decimal_aceito(amount: object) -> None:
    payload = _api01()
    payload["transactions"][0]["amount_brl"] = amount
    assert isinstance(Alert.model_validate(payload).transactions[0].amount_brl, Decimal)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("alert_id",), "nao-e-uuid"),
        (("selected_at",), "2026-09-15T13:00:00"),
        (("transactions",), []),
        (("occurrence_window",), {"start": "2026-09-14T00:00:00Z", "end": "2026-09-08T00:00:00Z"}),
        (("extra_field",), "x"),
        (("sender_customer", "email"), "x"),
    ],
)
def test_dt_ingestao_alerta_invalido(path: tuple[str, ...], value: object) -> None:
    payload = _api01()
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValidationError):
        Alert.model_validate(payload)


# DT-03 -----------------------------------------------------------------------


def test_dt_ingestao_cliente_sintetico_valido() -> None:
    customer = SyntheticCustomer.model_validate(
        {
            "customer_id": "cust-0001",
            "name": "Cliente Sintético Um",
            "cpf_cnpj": _runtime_cpf_like(),
            "accounts": ["0001-0012345-6"],
            "segment": "PF",
            "restriction_flags": [],
        }
    )
    assert customer.accounts == ["0001-0012345-6"]


# DT-04 -----------------------------------------------------------------------


def test_dt_ingestao_alerta_sanitizado_valido() -> None:
    sanitized = SanitizedAlert.model_validate(_sanitized())
    assert sanitized.pii_token_count == 3
    assert sanitized.sender_customer.cpf_cnpj == "CPF_01"


def test_dt_ingestao_sanitizado_tem_campos_do_dt01_mais_metadados() -> None:
    assert set(SanitizedAlert.model_fields) == set(Alert.model_fields) | {"pii_token_count", "sanitizer_version"}


@pytest.mark.parametrize(
    ("path", "raw"),
    [
        (("sender_account",), "0001-0012345-6"),
        (("sender_customer", "name"), "Cliente Sintético Um"),
        (("sender_customer", "cpf_cnpj"), None),
        (("transactions", 0, "sender_account"), "0001-0012345-6"),
        (("transactions", 0, "receiver_account"), "0001-0012345-6"),
    ],
)
def test_dt_ingestao_sanitizado_rejeita_dado_pessoal_em_claro(path: tuple[str | int, ...], raw: str | None) -> None:
    payload = _sanitized()
    target: Any = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = raw if raw is not None else _runtime_cpf_like()
    with pytest.raises(ValidationError):
        SanitizedAlert.model_validate(payload)


@pytest.mark.parametrize(("field", "value"), [("pii_token_count", -1), ("sanitizer_version", "")])
def test_dt_ingestao_sanitizado_metadados_invalidos(field: str, value: object) -> None:
    payload = _sanitized()
    payload[field] = value
    with pytest.raises(ValidationError):
        SanitizedAlert.model_validate(payload)


@pytest.mark.parametrize(
    ("model", "dt_id"),
    [
        (Alert, "DT-01"),
        (Transaction, "DT-02"),
        (SyntheticCustomer, "DT-03"),
        (SanitizedAlert, "DT-04"),
        (AlertRecord, "DT-05"),
    ],
)
def test_dt_ingestao_docstring_cita_dt(model: type[BaseModel], dt_id: str) -> None:
    assert dt_id in (model.__doc__ or "")
