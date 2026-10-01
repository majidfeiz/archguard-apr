"""Provider-neutral contracts for paid model inference."""

import re
from dataclasses import asdict, dataclass
from enum import StrEnum

from archguard.domain.orchestration import AgentRole, fingerprint
from archguard.domain.repository import check, digest

PROVIDER_CONFIG_SCHEMA = "archguard.provider-config/v1"
PROVIDER_INVOCATION_SCHEMA = "archguard.provider-invocation/v1"


class ProviderCapability(StrEnum):
    STRUCTURED_OUTPUT = "structured_output"
    STRICT_JSON_SCHEMA = "strict_json_schema"
    TOOL_STRUCTURED_RESPONSE = "tool_structured_response"
    CONFIGURABLE_REASONING = "configurable_reasoning"
    USAGE_REPORTING = "usage_reporting"
    STREAMING = "streaming"
    REQUEST_CANCELLATION = "request_cancellation"
    STATELESS_OPERATION = "stateless_operation"
    PROMPT_CACHING = "prompt_caching"
    REQUEST_ID = "provider_request_id"
    SERVER_DATA_CONTROLS = "server_side_data_controls"


@dataclass(frozen=True)
class ProviderCapabilities:
    provider: str
    values: frozenset[ProviderCapability]

    def __post_init__(self) -> None:
        check(self.provider in {"openai", "anthropic"}, "unknown provider")
        object.__setattr__(self, "values", frozenset(self.values))
        check(ProviderCapability.STRUCTURED_OUTPUT in self.values, "structured output required")
        check(
            ProviderCapability.STRICT_JSON_SCHEMA in self.values
            or ProviderCapability.TOOL_STRUCTURED_RESPONSE in self.values,
            "contradictory provider capabilities",
        )

    def require(self, required: frozenset[ProviderCapability]) -> None:
        check(required <= self.values, "unsupported provider capability")


class ProviderErrorCategory(StrEnum):
    AUTHENTICATION = "authentication_failure"
    PERMISSION = "permission_failure"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED_MODEL = "unsupported_model"
    RATE_LIMITED = "rate_limited"
    OVERLOADED = "provider_overloaded"
    UNAVAILABLE = "provider_unavailable"
    NETWORK = "network_failure"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    REFUSAL = "refusal"
    INCOMPLETE = "incomplete_response"
    OUTPUT_LIMIT = "output_limit_exceeded"
    MALFORMED_OUTPUT = "malformed_structured_output"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"
    BUDGET_REJECTED = "budget_rejected"
    INTERNAL = "internal_adapter_error"


@dataclass(frozen=True)
class ProviderFailure:
    category: ProviderErrorCategory
    retryable: bool
    public_message: str
    provider: str
    stage: str
    retry_after_seconds: float | None = None
    provider_code: str | None = None
    request_id: str | None = None

    def __post_init__(self) -> None:
        check(self.provider in {"openai", "anthropic"}, "unknown provider")
        check(re.fullmatch(r"[a-z_]{1,64}", self.stage) is not None, "invalid operation stage")
        check(0 < len(self.public_message) <= 512, "invalid public error")
        if self.retry_after_seconds is not None:
            check(0 <= self.retry_after_seconds <= 3600, "invalid retry-after")


@dataclass(frozen=True)
class ProviderUsage:
    input_units: int
    output_units: int
    cached_input_units: int | None
    reasoning_units: int | None
    provider: str
    model: str
    request_count: int = 1

    def __post_init__(self) -> None:
        values = (self.input_units, self.output_units, self.request_count)
        check(
            all(isinstance(value, int) and 0 <= value <= 10_000_000 for value in values),
            "invalid usage",
        )
        for value in (self.cached_input_units, self.reasoning_units):
            check(value is None or 0 <= value <= 10_000_000, "invalid usage detail")


@dataclass(frozen=True)
class ProviderInvocation:
    schema: str
    provider: str
    configured_model: str
    returned_model: str
    role: AgentRole
    request_schema_fingerprint: str
    prompt_template_fingerprint: str
    input_artifact_references: tuple[str, ...]
    response_schema_fingerprint: str
    output_fingerprint: str
    usage: ProviderUsage
    status: str
    request_id_hash: str | None = None
    invocation_fingerprint: str = ""

    def __post_init__(self) -> None:
        check(self.schema == PROVIDER_INVOCATION_SCHEMA, "unsupported invocation schema")
        for value in (
            self.request_schema_fingerprint,
            self.prompt_template_fingerprint,
            self.response_schema_fingerprint,
            self.output_fingerprint,
        ):
            digest(value)
        if self.request_id_hash is not None:
            digest(self.request_id_hash)
        object.__setattr__(
            self, "input_artifact_references", tuple(sorted(self.input_artifact_references))
        )
        expected = fingerprint(
            {k: v for k, v in asdict(self).items() if k != "invocation_fingerprint"}
        )
        if self.invocation_fingerprint:
            check(self.invocation_fingerprint == expected, "invocation fingerprint mismatch")
        else:
            object.__setattr__(self, "invocation_fingerprint", expected)
