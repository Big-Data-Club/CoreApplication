"""
Symmetric encryption for LLM provider API keys.
 
The master secret is read from settings.ai_key_encryption_secret. It MUST
be a urlsafe base64-encoded 32-byte key (Fernet format). To generate one:
 
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
 
Design:
  * Plaintext keys never leave this module except via `decrypt()` inside the
    gateway at call time. They are never logged.
  * `fingerprint()` returns a short, non-reversible label (first 4 / last 4 of
    the plaintext) for admin UI display.
  * If the secret is missing in dev we fall back to a deterministic dev key
    derived from the service secret, with a loud warning. Production deployments
    MUST override it explicitly.
"""
from __future__ import annotations
 
import base64
import hashlib
import logging
from functools import lru_cache
 
from cryptography.fernet import Fernet, InvalidToken
 
from app.core.config import get_settings
 
logger = logging.getLogger(__name__)
 
 
class KeyCryptoError(RuntimeError):
    """Raised when an API key cannot be encrypted or decrypted."""
 
 
@lru_cache(maxsize=1)
def _cipher() -> Fernet:
    settings = get_settings()
    raw = (settings.ai_key_encryption_secret or "").strip()
 
    if not raw:
        # Dev fallback: derive a stable key from ai_service_secret so local
        # restarts don't invalidate stored rows. Log a loud warning.
        digest = hashlib.sha256(settings.ai_service_secret.encode()).digest()
        raw = base64.urlsafe_b64encode(digest).decode()
        logger.warning(
            "AI_KEY_ENCRYPTION_SECRET is not set; using a derived dev key. "
            "Set a proper Fernet key in production."
        )
 
    try:
        return Fernet(raw.encode() if isinstance(raw, str) else raw)
    except Exception as exc:  # ValueError on malformed key
        raise KeyCryptoError(
            "AI_KEY_ENCRYPTION_SECRET is not a valid Fernet key. "
            "Generate one with Fernet.generate_key()."
        ) from exc
 
 
def encrypt(plaintext: str) -> str:
    if not plaintext:
        raise KeyCryptoError("Refusing to encrypt empty API key.")
    return _cipher().encrypt(plaintext.encode()).decode()
 
 
def decrypt(ciphertext: str) -> str:
    try:
        return _cipher().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise KeyCryptoError(
            "Cannot decrypt API key - encryption secret changed or ciphertext corrupted."
        ) from exc
 
 
def fingerprint(plaintext: str) -> str:
    """Short non-reversible label for admin display."""
    p = plaintext.strip()
    if len(p) <= 8:
        return "*" * len(p)
    return f"{p[:4]}…{p[-4:]}"