"""PBKDF2 password hashes. Stdlib only."""

from __future__ import annotations

import hashlib
import hmac
import os

_ROUNDS = 100_000


def hash_password(password: str, salt: bytes | None = None) -> str:
    """Return salt:digest hex. Generate a salt when one is not supplied."""
    raw_salt = salt if salt is not None else os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), raw_salt, _ROUNDS)
    return raw_salt.hex() + ":" + digest.hex()


def verify_password(password: str, stored: str) -> bool:
    """True when password matches a hash_password() string."""
    salt_hex, _, digest_hex = stored.partition(":")
    if not salt_hex or not digest_hex:
        return False
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    candidate = hash_password(password, salt)
    return hmac.compare_digest(candidate, stored)
