"""Phase 13 provider configuration loading and check-only preflight."""

import json
import os
import platform
import shutil
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from archguard.domain.provider_preflight import (
    ProviderExperimentConfiguration,
    TokenPrices,
)


def load_phase13_provider_configuration(path: Path) -> ProviderExperimentConfiguration:
    raw = json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)
    if not isinstance(raw, dict) or set(raw) != _configuration_keys():
        raise ValueError("invalid provider configuration shape")
    prices = raw.pop("prices")
    if not isinstance(prices, dict):
        raise ValueError("invalid price table")
    for key in ("input", "cached_input", "output"):
        prices[key] = Decimal(str(prices[key]))
    raw["prices"] = TokenPrices(**prices)
    raw["temperature"] = Decimal(str(raw["temperature"]))
    raw["warning_cost_usd"] = Decimal(str(raw["warning_cost_usd"]))
    raw["hard_cost_usd"] = Decimal(str(raw["hard_cost_usd"]))
    raw["retryable_error_classes"] = tuple(raw["retryable_error_classes"])
    return ProviderExperimentConfiguration(**raw)


def canonical_configuration_bytes(configuration: ProviderExperimentConfiguration) -> bytes:
    value = _json_value(asdict(configuration))
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode()


def provider_preflight(
    configuration: ProviderExperimentConfiguration,
    *,
    output_directory: Path,
    analyzed_roots: tuple[Path, ...],
    require_secret: bool = True,
) -> dict[str, Any]:
    secret_present = bool(os.environ.get("OPENAI_API_KEY"))
    output = output_directory.resolve()
    roots = tuple(root.resolve() for root in analyzed_roots)
    output_separate = all(output != root and root not in output.parents for root in roots)
    checks = {
        "configuration_fingerprint": bool(configuration.provider_configuration_fingerprint),
        "cost_ceiling": configuration.maximum_call_cost() * configuration.maximum_provider_calls
        <= configuration.hard_cost_usd,
        "docker_available": shutil.which("docker") is not None,
        "linux_x86_64": platform.system() == "Linux" and platform.machine() in {"x86_64", "AMD64"},
        "model_snapshot": configuration.model == "gpt-5.4-2026-03-05",
        "output_directory_immutable": not output.exists(),
        "output_separate_from_analyzed_roots": output_separate,
        "population_binding": configuration.population_fingerprint
        == "421f3129ef6bee5883c41d05f087d6faff5b2a3de3b2ea543b4d27ade1488886",
        "pricing_source": configuration.prices.source_url
        == "https://developers.openai.com/api/docs/models/gpt-5.4",
        "pricing_fresh": _pricing_is_fresh(configuration.prices.verified_at),
        "protocol_binding": configuration.protocol_fingerprint
        == "93494690f402d17e511d9cad1fdc92907d408ae3a923139d30537894f9ab8ce7",
        "secret_present": secret_present if require_secret else True,
    }
    return {
        "schema": "archguard.provider-preflight/v1",
        "status": "ready" if all(checks.values()) else "blocked",
        "mode": "offline",
        "network_request": False,
        "checks": checks,
        "provider_configuration_fingerprint": configuration.provider_configuration_fingerprint,
    }


def _pricing_is_fresh(value: str) -> bool:
    try:
        verified = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    age = datetime.now(UTC) - verified
    return timedelta(0) <= age <= timedelta(days=30)


def _configuration_keys() -> set[str]:
    return {
        "schema_version",
        "provider",
        "model",
        "model_snapshot_pinned",
        "endpoint",
        "temperature",
        "seed",
        "seed_supported",
        "maximum_input_tokens",
        "maximum_output_tokens",
        "context_limit",
        "concurrency",
        "timeout_seconds",
        "retry_count",
        "retryable_error_classes",
        "maximum_provider_calls",
        "planned_primary_executions",
        "warning_cost_usd",
        "hard_cost_usd",
        "prices",
        "population_fingerprint",
        "protocol_fingerprint",
        "provider_configuration_fingerprint",
    }


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value
