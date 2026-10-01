"""Strict versioned provider configuration loading."""

import os
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from archguard.domain.orchestration import AgentRole


class RetryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    maximum_attempts: int = Field(default=3, ge=1, le=6)
    maximum_delay_seconds: float = Field(default=30, gt=0, le=300, allow_inf_nan=False)


class ProviderSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    provider: Literal["openai", "anthropic"]
    model: str
    endpoint_mode: Literal["official"] = "official"
    request_timeout_seconds: float = Field(default=60, gt=0, le=600, allow_inf_nan=False)
    connect_timeout_seconds: float = Field(default=10, gt=0, le=60, allow_inf_nan=False)
    maximum_output_units: int = Field(default=2048, gt=0, le=100_000)
    retry: RetryPolicy = RetryPolicy()
    structured_output_mode: Literal["strict_json_schema", "forced_tool"]
    temperature: float | None = Field(default=None, ge=0, le=2, allow_inf_nan=False)
    reasoning_effort: Literal["minimal", "low", "medium", "high"] | None = None
    organization_env: str | None = None
    project_env: str | None = None
    stateless: bool = True
    model_allowlist: tuple[str, ...]
    maximum_invocation_cost: str | None = None

    @field_validator("model")
    @classmethod
    def nonempty_model(cls, value: str) -> str:
        if not value.strip() or "api_key" in value.lower():
            raise ValueError("invalid model identifier")
        return value

    @field_validator("organization_env", "project_env")
    @classmethod
    def environment_reference(cls, value: str | None) -> str | None:
        if value is not None and re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", value) is None:
            raise ValueError("invalid environment variable reference")
        return value

    @model_validator(mode="after")
    def compatible(self) -> "ProviderSettings":
        if self.model not in self.model_allowlist:
            raise ValueError("model not allowlisted")
        if self.provider == "openai" and self.structured_output_mode != "strict_json_schema":
            raise ValueError("unsupported OpenAI output mode")
        return self


class ProviderConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    schema_version: Literal["archguard.provider-config/v1"] = "archguard.provider-config/v1"
    providers: tuple[ProviderSettings, ...]
    role_to_provider: dict[AgentRole, str]
    role_to_model: dict[AgentRole, str] = Field(default_factory=dict)
    live_execution_enabled: bool = False
    prompt_logging_enabled: bool = False
    response_logging_enabled: bool = False

    @model_validator(mode="after")
    def mappings_are_known(self) -> "ProviderConfiguration":
        names = {item.provider for item in self.providers}
        if len(names) != len(self.providers):
            raise ValueError("duplicate provider")
        llm_roles = set(AgentRole) - {AgentRole.COORDINATOR, AgentRole.HUMAN_GATE}
        if set(self.role_to_provider) != llm_roles:
            raise ValueError("unknown or missing role mapping")
        if not set(self.role_to_provider.values()) <= names:
            raise ValueError("role references unknown provider")
        if not set(self.role_to_model) <= llm_roles:
            raise ValueError("unknown role model mapping")
        available = {item.model for item in self.providers}
        if not set(self.role_to_model.values()) <= available:
            raise ValueError("role references unknown model")
        return self


def _expand_models(value: object) -> object:
    if isinstance(value, dict):
        return {key: _expand_models(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand_models(item) for item in value]
    if isinstance(value, str):
        match = re.fullmatch(r"\$\{(OPENAI_MODEL|ANTHROPIC_MODEL)\}", value)
        if match:
            resolved = os.environ.get(match.group(1), "")
            if not resolved:
                raise ValueError("configured model environment variable is not set")
            return resolved
    return value


def load_provider_configuration(path: Path) -> ProviderConfiguration:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        raise ValueError("invalid provider configuration YAML") from None
    if not isinstance(data, dict):
        raise ValueError("provider configuration must be a mapping")
    forbidden = {"api_key", "openai_api_key", "anthropic_api_key", "base_url", "endpoint"}
    if any(key.lower() in forbidden for key in _keys(data)):
        raise ValueError("credentials and custom endpoints are forbidden")
    return ProviderConfiguration.model_validate(_expand_models(data))


def _keys(value: object) -> list[str]:
    if isinstance(value, dict):
        return [str(key) for key in value] + [key for item in value.values() for key in _keys(item)]
    if isinstance(value, list):
        return [key for item in value for key in _keys(item)]
    return []
