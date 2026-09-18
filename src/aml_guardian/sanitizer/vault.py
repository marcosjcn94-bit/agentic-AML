"""In-memory AES-GCM Vault for PII tokens (ADR-012)."""

import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class KeyProvider:
    """Provides cryptographic keys for Vault encryption."""

    def __init__(self, password: str | None = None):
        """Initialize with optional password. If not provided, generate random key."""
        if password:
            # Derive key from password
            salt = b"aml_guardian_salt"  # Fixed salt for consistency
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            self.key = kdf.derive(password.encode())
        else:
            # Generate random 256-bit key
            self.key = os.urandom(32)


class Vault:
    """In-memory AES-GCM vault for storing PII token mappings (never persisted)."""

    def __init__(self, key_provider: KeyProvider | None = None):
        """Initialize vault with optional key provider."""
        if key_provider is None:
            key_provider = KeyProvider()
        self.key_provider = key_provider
        self.vault: dict[str, bytes] = {}  # token -> encrypted_value

    def store(self, token: str, value: str) -> None:
        """Store a value in the vault encrypted."""
        cipher = AESGCM(self.key_provider.key)
        nonce = os.urandom(12)
        ciphertext = cipher.encrypt(nonce, value.encode(), None)
        # Store nonce + ciphertext
        self.vault[token] = nonce + ciphertext

    def retrieve(self, token: str) -> str | None:
        """Retrieve a value from the vault."""
        if token not in self.vault:
            return None
        cipher = AESGCM(self.key_provider.key)
        data = self.vault[token]
        nonce = data[:12]
        ciphertext = data[12:]
        try:
            plaintext = cipher.decrypt(nonce, ciphertext, None)
            return plaintext.decode()
        except Exception:
            return None

    def keys(self) -> list[str]:
        """Get all tokens in the vault."""
        return list(self.vault.keys())

    def clear(self) -> None:
        """Clear all entries in the vault."""
        self.vault.clear()

    def __len__(self) -> int:
        """Get the number of entries in the vault."""
        return len(self.vault)
