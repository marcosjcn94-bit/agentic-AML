"""MCP-01 (get_customer_history) and MCP-02 (check_restriction_lists) servers."""

from typing import Any


def get_customer_history(customer_id: str, window_days: int = 30) -> dict[str, Any]:
    """MCP-01 server: Retrieve customer transaction history.

    Args:
        customer_id: Customer identifier (token or ID)
        window_days: Number of days to look back (max 180)

    Returns:
        Dict with transaction history or error
    """
    # Validate window_days
    if window_days > 180 or window_days < 1:
        return {
            "error": "INVALID_PARAMETER",
            "message": f"window_days must be between 1 and 180, got {window_days}",
            "retryable": False,
        }

    # Mock implementation - in production this queries core_sintetico.sqlite
    # and sanitizes the output before returning via Sanitizer

    return {
        "status": "success",
        "customer_id": customer_id,
        "window_days": window_days,
        "transactions": [
            {
                "transaction_id": "TXN_001",
                "timestamp": "2026-09-10T10:30:00Z",
                "amount_brl": "1000.00",
                "payment_type": "PIX",
                "sender_account": "CONTA_01",  # Already tokenized
                "receiver_account": "CONTA_02",  # Already tokenized
            }
        ],
        "total_amount": "1000.00",
        "transaction_count": 1,
    }


def check_restriction_lists(customer_id: str, cpf_cnpj_token: str = None) -> dict[str, Any]:
    """MCP-02 server: Check customer against restriction lists (PEP, CEIS, CNEP).

    Args:
        customer_id: Customer identifier
        cpf_cnpj_token: PII token for document number

    Returns:
        Dict with restriction status
    """
    # Mock implementation - in production this queries PEP/CEIS/CNEP lists
    # Output contains only flags, no PII

    return {
        "status": "success",
        "customer_id": customer_id,
        "pep": "nao",  # PEP (Pessoa Politicamente Exposta)
        "ceis": "nao",  # CEIS (Cadastro de Entidades Inativas)
        "cnep": "nao",  # CNEP (Cadastro Nacional de Empresas Punidas)
        "list_version": "2026-09-17",
        "checked_at": "2026-09-17T14:30:00Z",
    }
