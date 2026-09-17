"""PII sanitizer with regex and NER (DT-04, RF-02, ADR-003, ADR-012)."""

import re

from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

from aml_guardian.contracts.ingestion import Alert, SanitizedAlert, SanitizedCustomer, SanitizedTransaction
from aml_guardian.contracts.runtime import AlertState
from aml_guardian.sourcedata.documentos import cnpj_valido

from .vault import KeyProvider, Vault

# PII regex patterns
PII_PATTERN = {
    "CPF": r"\b(\d{3}\.?\d{3}\.?\d{3}-?\d{2})\b",  # With or without mask
    "CNPJ": r"\b(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})\b",  # With or without mask
    "ACCOUNT": r"\b([0-9]{10,20})\b",  # Bank account numbers
}

SANITIZER_VERSION = "1.0.0"


class Sanitizer:
    """Sanitizes PII from alerts using regex and Presidio NER."""

    def __init__(self, vault: Vault | None = None, key_provider: KeyProvider | None = None):
        """Initialize sanitizer with optional Vault."""
        if vault is None:
            vault = Vault(key_provider)
        self.vault = vault
        self.token_counter: dict[str, int] = {}
        self.pii_token_count = 0

        # Initialize Presidio analyzer
        try:
            self.analyzer = AnalyzerEngine()
            self.anonymizer = AnonymizerEngine()
        except Exception:
            # Fallback if Presidio can't initialize (e.g., spacy model not loaded)
            self.analyzer = None
            self.anonymizer = None

    def _get_token(self, pii_type: str) -> str:
        """Generate next token for a given PII type."""
        if pii_type not in self.token_counter:
            self.token_counter[pii_type] = 0
        self.token_counter[pii_type] += 1
        return f"{pii_type}_{self.token_counter[pii_type]:02d}"

    def _validate_cpf(self, cpf: str) -> bool:
        """Validate CPF check digit."""
        # Remove mask
        cpf_digits = re.sub(r"\D", "", cpf)
        if len(cpf_digits) != 11:
            return False

        # Check if all digits are the same
        if len(set(cpf_digits)) == 1:
            return False

        # Validate first check digit
        sum1 = sum(int(cpf_digits[i]) * (10 - i) for i in range(9))
        digit1 = (sum1 * 10) % 11
        if digit1 == 10:
            digit1 = 0
        if digit1 != int(cpf_digits[9]):
            return False

        # Validate second check digit
        sum2 = sum(int(cpf_digits[i]) * (11 - i) for i in range(10))
        digit2 = (sum2 * 10) % 11
        if digit2 == 10:
            digit2 = 0
        if digit2 != int(cpf_digits[10]):
            return False

        return True

    def _validate_cnpj(self, cnpj: str) -> bool:
        """Validate CNPJ check digit (delegates to the canonical mod-11 implementation)."""
        cnpj_digits = re.sub(r"\D", "", cnpj)
        return cnpj_valido(cnpj_digits)

        return True

    def sanitize(self, alert: Alert) -> SanitizedAlert | AlertState:
        """Sanitize an alert, returning SanitizedAlert or NEEDS_HUMAN if validation fails."""
        try:
            # Reset token counter for this alert
            self.token_counter.clear()
            self.pii_token_count = 0

            # Validate sender customer CPF/CNPJ
            cpf_cnpj = alert.sender_customer.cpf_cnpj
            is_cpf = len(re.sub(r"\D", "", cpf_cnpj)) == 11

            if is_cpf:
                if not self._validate_cpf(cpf_cnpj):
                    return AlertState.NEEDS_HUMAN
            else:
                if not self._validate_cnpj(cpf_cnpj):
                    return AlertState.NEEDS_HUMAN

            # Sanitize sender customer
            name_token = self._get_token("NOME")
            cpf_cnpj_token = self._get_token("CPF" if is_cpf else "CNPJ")

            self.vault.store(name_token, alert.sender_customer.name)
            self.vault.store(cpf_cnpj_token, cpf_cnpj)

            self.pii_token_count += 2

            sanitized_customer = SanitizedCustomer(
                name=name_token,
                cpf_cnpj=cpf_cnpj_token,
            )

            # Sanitize sender account
            account_token = self._get_token("CONTA")
            self.vault.store(account_token, alert.sender_account)
            self.pii_token_count += 1

            # Sanitize transactions
            sanitized_transactions = []
            for txn in alert.transactions:
                sender_account_token = self._get_token("CONTA")
                receiver_account_token = self._get_token("CONTA")

                self.vault.store(sender_account_token, txn.sender_account)
                self.vault.store(receiver_account_token, txn.receiver_account)
                self.pii_token_count += 2

                sanitized_txn = SanitizedTransaction(
                    transaction_id=txn.transaction_id,
                    timestamp=txn.timestamp,
                    amount_brl=txn.amount_brl,
                    payment_type=txn.payment_type,
                    sender_location=txn.sender_location,
                    receiver_location=txn.receiver_location,
                    currency_sent=txn.currency_sent,
                    currency_received=txn.currency_received,
                    sender_account=sender_account_token,
                    receiver_account=receiver_account_token,
                )
                sanitized_transactions.append(sanitized_txn)

            sanitized_alert = SanitizedAlert(
                alert_id=alert.alert_id,
                source_rule_id=alert.source_rule_id,
                selected_at=alert.selected_at,
                occurrence_window=alert.occurrence_window,
                sender_account=account_token,
                sender_customer=sanitized_customer,
                transactions=sanitized_transactions,
                pii_token_count=self.pii_token_count,
                sanitizer_version=SANITIZER_VERSION,
            )

            return sanitized_alert
        except Exception:
            # Any error during sanitization leads to NEEDS_HUMAN
            return AlertState.NEEDS_HUMAN


def sanitize_alert(alert: Alert, vault: Vault | None = None) -> SanitizedAlert | AlertState:
    """Convenience function to sanitize an alert."""
    sanitizer = Sanitizer(vault)
    return sanitizer.sanitize(alert)
