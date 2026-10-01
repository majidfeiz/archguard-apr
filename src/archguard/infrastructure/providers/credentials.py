"""Minimal environment-only credential acquisition."""

import os
from dataclasses import dataclass


@dataclass(frozen=True, repr=False)
class ProviderCredential:
    configured: bool
    _value: str | None

    def reveal_for_client(self) -> str:
        if not self._value:
            raise ValueError("provider credential is not configured")
        return self._value


def credential_for(provider: str) -> ProviderCredential:
    name = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}.get(provider)
    if name is None:
        raise ValueError("unknown provider")
    value = os.environ.get(name)
    return ProviderCredential(bool(value), value)
