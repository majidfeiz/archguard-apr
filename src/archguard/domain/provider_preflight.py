"""Immutable Phase 13 provider policy and deterministic cost accounting."""

from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any, cast

from archguard.domain.orchestration import fingerprint
from archguard.domain.repository import check, digest

PROVIDER_CONFIGURATION_SCHEMA = "archguard.phase-13-provider-configuration/v1"
USAGE_SCHEMA = "archguard.provider-usage/v1"


@dataclass(frozen=True)
class TokenPrices:
    currency: str
    unit_tokens: int
    input: Decimal
    cached_input: Decimal
    output: Decimal
    verified_at: str
    source_url: str

    def __post_init__(self) -> None:
        check(self.currency == "USD", "unsupported pricing currency")
        check(self.unit_tokens == 1_000_000, "unsupported pricing unit")
        check(
            all(value >= 0 for value in (self.input, self.cached_input, self.output)),
            "invalid price",
        )
        check(
            self.source_url.startswith("https://developers.openai.com/"), "unofficial price source"
        )
        check(self.verified_at.endswith("Z"), "pricing timestamp must be UTC")


@dataclass(frozen=True)
class ProviderExperimentConfiguration:
    schema_version: str
    provider: str
    model: str
    model_snapshot_pinned: bool
    endpoint: str
    temperature: Decimal
    seed: int | None
    seed_supported: bool
    maximum_input_tokens: int
    maximum_output_tokens: int
    context_limit: int
    concurrency: int
    timeout_seconds: int
    retry_count: int
    retryable_error_classes: tuple[str, ...]
    maximum_provider_calls: int
    planned_primary_executions: int
    warning_cost_usd: Decimal
    hard_cost_usd: Decimal
    prices: TokenPrices
    population_fingerprint: str
    protocol_fingerprint: str
    provider_configuration_fingerprint: str = ""

    def __post_init__(self) -> None:
        check(self.schema_version == PROVIDER_CONFIGURATION_SCHEMA, "unsupported provider schema")
        check(self.provider == "openai", "unsupported provider")
        check(
            self.model_snapshot_pinned and self.model == "gpt-5.4-2026-03-05",
            "unknown model identity",
        )
        check(self.endpoint == "https://api.openai.com/v1/responses", "unexpected endpoint")
        check(self.temperature == 0, "temperature must be zero")
        check(self.seed is None and not self.seed_supported, "unsupported seed configuration")
        check(0 < self.maximum_input_tokens <= self.context_limit, "invalid input limit")
        check(0 < self.maximum_output_tokens <= 128_000, "invalid output limit")
        check(
            self.maximum_input_tokens + self.maximum_output_tokens <= self.context_limit,
            "context limit exceeded",
        )
        check(self.concurrency == 1, "concurrency must be one")
        check(0 < self.timeout_seconds <= 1200, "invalid timeout")
        check(self.retry_count == 1, "retry count must be one")
        check(
            self.retryable_error_classes
            == ("connection_failure", "provider_5xx", "rate_limit", "timeout"),
            "invalid retry policy",
        )
        check(self.planned_primary_executions == 6, "invalid primary execution count")
        check(self.maximum_provider_calls == 12, "invalid provider call ceiling")
        check(Decimal("0") < self.warning_cost_usd < self.hard_cost_usd, "invalid cost thresholds")
        check(
            self.warning_cost_usd == Decimal("15") and self.hard_cost_usd == Decimal("20"),
            "cost policy mismatch",
        )
        digest(self.population_fingerprint)
        digest(self.protocol_fingerprint)
        expected = fingerprint(self.fingerprint_payload())
        if self.provider_configuration_fingerprint:
            check(
                self.provider_configuration_fingerprint == expected,
                "provider configuration fingerprint mismatch",
            )
        else:
            object.__setattr__(self, "provider_configuration_fingerprint", expected)

    def fingerprint_payload(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("provider_configuration_fingerprint", None)
        return cast(dict[str, Any], _decimal_strings(value))

    def maximum_call_cost(self) -> Decimal:
        return (
            Decimal(self.maximum_input_tokens) * self.prices.input
            + Decimal(self.maximum_output_tokens) * self.prices.output
        ) / Decimal(self.prices.unit_tokens)


@dataclass(frozen=True)
class ProviderUsageRecord:
    schema: str
    model: str
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int

    def __post_init__(self) -> None:
        check(self.schema == USAGE_SCHEMA, "unsupported usage schema")
        check(self.model == "gpt-5.4-2026-03-05", "unknown model identity")
        values = (self.input_tokens, self.cached_input_tokens, self.output_tokens)
        check(
            all(
                isinstance(value, int) and not isinstance(value, bool) and value >= 0
                for value in values
            ),
            "invalid usage",
        )
        check(self.cached_input_tokens <= self.input_tokens, "cached input exceeds input")


@dataclass(frozen=True)
class CostGuard:
    configuration: ProviderExperimentConfiguration

    def authorize(self, observed_cost_usd: Decimal, calls_started: int) -> Decimal:
        check(observed_cost_usd >= 0, "invalid observed cost")
        check(
            0 <= calls_started < self.configuration.maximum_provider_calls,
            "provider call ceiling reached",
        )
        check(
            observed_cost_usd < self.configuration.warning_cost_usd,
            "emergency cost threshold reached",
        )
        estimate = self.configuration.maximum_call_cost()
        check(
            observed_cost_usd + estimate <= self.configuration.hard_cost_usd,
            "hard cost ceiling would be exceeded",
        )
        return estimate

    def observed_cost(self, usage: ProviderUsageRecord) -> Decimal:
        check(usage.model == self.configuration.model, "unknown model identity")
        uncached = usage.input_tokens - usage.cached_input_tokens
        return (
            Decimal(uncached) * self.configuration.prices.input
            + Decimal(usage.cached_input_tokens) * self.configuration.prices.cached_input
            + Decimal(usage.output_tokens) * self.configuration.prices.output
        ) / Decimal(self.configuration.prices.unit_tokens)


def _decimal_strings(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return cast(dict[str, Any], {key: _decimal_strings(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return [_decimal_strings(item) for item in value]
    return value
