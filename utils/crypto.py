import base64
import logging
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings

logger = logging.getLogger(__name__)

# GCM nonce length — NIST recommends 96 bits (12 bytes).
_NONCE_BYTES = 12


def _get_key() -> bytes:
    hex_key: str = getattr(settings, "TOKEN_ENCRYPTION_KEY", "")
    if not hex_key:
        raise ValueError(
            "TOKEN_ENCRYPTION_KEY is not configured. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    try:
        raw = bytes.fromhex(hex_key)
    except ValueError as exc:
        raise ValueError("TOKEN_ENCRYPTION_KEY must be a 64-character hex string.") from exc

    if len(raw) != 32:
        raise ValueError(
            f"TOKEN_ENCRYPTION_KEY must decode to exactly 32 bytes, got {len(raw)}."
        )
    return raw


def encrypt_token(plaintext: str) -> str:
    key = _get_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ciphertext).decode()


def decrypt_token(encrypted: str) -> str:
    key = _get_key()
    aesgcm = AESGCM(key)
    raw = base64.b64decode(encrypted)
    nonce, ciphertext = raw[:_NONCE_BYTES], raw[_NONCE_BYTES:]
    return aesgcm.decrypt(nonce, ciphertext, None).decode()
