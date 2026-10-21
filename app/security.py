"""Password hashing and opaque session tokens.

Passwords are PBKDF2-HMAC-SHA256 with a per-user random salt and 200k
iterations. Nothing here ever logs or echoes a password.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 200_000
SALT_BYTES = 16


def hash_password(password: str) -> str:
    """Hash a password into ``pbkdf2_sha256$iterations$salt_hex$digest_hex``."""
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return f"{ALGORITHM}${ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    """Constant-time password check against a stored hash."""
    if not stored or password is None:
        return False
    try:
        algorithm, iterations, salt_hex, digest_hex = stored.split("$")
        if algorithm != ALGORITHM:
            return False
        salt = bytes.fromhex(salt_hex)
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate.hex(), digest_hex)


def new_token(nbytes: int = 32) -> str:
    """An unguessable URL-safe token used for session ids and CSRF values."""
    return secrets.token_urlsafe(nbytes)
