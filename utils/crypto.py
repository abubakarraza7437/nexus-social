"""
Utils — AES-256-GCM Token Encryption
======================================
OAuth access/refresh tokens are encrypted at rest using AES-256-GCM.

Envelope encryption pattern:
  - Each token is encrypted with a Data Encryption Key (DEK).
  - The DEK itself is encrypted with AWS KMS (Key Encryption Key / KEK).
  - Key rotation re-encrypts only the DEK, not every token.

For local / non-AWS environments the raw 32-byte hex key from
TOKEN_ENCRYPTION_KEY is used directly (no KMS).

Usage:
    encrypted = encrypt_token("my_oauth_access_token")
    plaintext = decrypt_token(encrypted)
"""

import base64
import logging
import os

from django.conf import settings

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

# GCM nonce length — NIST recommends 96 bits (12 bytes).
_NONCE_BYTES = 12


def _get_key() -> bytes:
    """
    Load the 32-byte (256-bit) encryption key from settings.
    Raises ValueError if the key is absent or malformed.
    """
    hex_key: str = getattr(settings, "TOKEN_ENCRYPTION_KEY", "")
    if not hex_key:
        raise ValueError(
            "TOKEN_ENCRYPTION_KEY is not configured. Generate one with: "
            'python -c "import secrets; print(secrets.token_hex(32))"'
        )
    try:
        raw = bytes.fromhex(hex_key)
    except ValueError as exc:
        raise ValueError("TOKEN_ENCRYPTION_KEY must be a 64-character hex string.") from exc

    if len(raw) != 32:
        raise ValueError(f"TOKEN_ENCRYPTION_KEY must decode to 32 bytes, got {len(raw)}.")
    return raw


def encrypt_token(plaintext: str) -> str:
    """
    Encrypt a plaintext string and return a base64-encoded ciphertext.

    Format (base64 decode): [ 12-byte nonce ][ ciphertext + 16-byte GCM tag ]
    """
    key = _get_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ciphertext).decode()


def decrypt_token(encrypted: str) -> str:
    """
    Decrypt a base64-encoded ciphertext produced by encrypt_token().
    Raises cryptography.exceptions.InvalidTag on tampered / corrupted data.
    """
    key = _get_key()
    aesgcm = AESGCM(key)
    raw = base64.b64decode(encrypted)
    nonce, ciphertext = raw[:_NONCE_BYTES], raw[_NONCE_BYTES:]
    return aesgcm.decrypt(nonce, ciphertext, None).decode()
