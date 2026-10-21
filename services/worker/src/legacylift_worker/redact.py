"""Redact secrets from text before it is sent to an LLM or embed API."""

from __future__ import annotations

import re

REPLACEMENT = "[REDACTED]"

_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        re.DOTALL,
    ),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(
        r"(?i)(api[_-]?key|secret|password|token|passwd|apikey)\s*[:=]\s*['\"][^'\"]{8,}['\"]"
    ),
    re.compile(
        r"(?i)(api[_-]?key|secret|password|token|passwd|apikey)=([^\s&'\"\\]{8,})"
    ),
    re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
)


def redact_secrets(text: str) -> str:
    """Replace credential-shaped spans with [REDACTED]."""
    redacted = text
    for pattern in _PATTERNS:
        redacted = pattern.sub(REPLACEMENT, redacted)
    return redacted
