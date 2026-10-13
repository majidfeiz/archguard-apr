"""Minimal environment-only credential acquisition."""

import os


class ProviderCredential:
    """Opaque runtime secret which cannot be serialized as a dataclass or mapping."""

    __slots__ = ("_configured", "_value")
    _configured: bool
    _value: str | None

    def __init__(self, configured: bool, value: str | None) -> None:
        object.__setattr__(self, "_configured", configured)
        object.__setattr__(self, "_value", value)

    @property
    def configured(self) -> bool:
        return self._configured

    def __repr__(self) -> str:
        return f"ProviderCredential(configured={self.configured!r})"

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
