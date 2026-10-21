"""JWT issue and verify. HS256 with JWT_SECRET from the environment."""

from __future__ import annotations

import os
from typing import Any

import jwt

from legacylift_orchestrator.models import User

ALGORITHM = "HS256"


def jwt_secret() -> str:
    return os.environ.get("JWT_SECRET", "").strip()


def issue_token(user: User) -> str:
    secret = jwt_secret()
    if not secret:
        raise RuntimeError("JWT_SECRET is empty")
    payload = {"sub": user.id, "name": user.username, "role": user.role}
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    secret = jwt_secret()
    if not secret:
        raise RuntimeError("JWT_SECRET is empty")
    payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
    if not isinstance(payload, dict):
        raise jwt.InvalidTokenError("JWT payload was not an object")
    return payload
