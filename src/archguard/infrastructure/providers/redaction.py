"""Sanitize identifiers and messages without leaking provider credentials."""

import hashlib
import os
import re


def request_id_hash(value: str | None) -> str | None:
    if not value or re.fullmatch(r"[A-Za-z0-9_.:-]{1,256}", value) is None:
        return None
    return hashlib.sha256(value.encode()).hexdigest()


def redact_provider_message(value: str) -> str:
    result = value
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        secret = os.environ.get(name)
        if secret:
            result = result.replace(secret, "[REDACTED]")
    result = re.sub(r"(?i)(authorization|api[-_ ]?key)\s*[:=]\s*\S+", r"\1=[REDACTED]", result)
    return result[:512]
