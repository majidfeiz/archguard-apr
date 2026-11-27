import json
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from archguard.domain.orchestration import fingerprint
from archguard.domain.provider_preflight import (
    CostGuard,
    CostGuardState,
    ProviderExperimentConfiguration,
    ProviderUsageRecord,
)
from archguard.infrastructure.provider_preflight import (
    canonical_configuration_bytes,
    load_phase13_provider_configuration,
    provider_preflight,
)


@pytest.fixture
def configuration(repository_root: Path) -> ProviderExperimentConfiguration:
    return load_phase13_provider_configuration(
        repository_root / "configs/experiments/phase13-provider.json"
    )


def test_configuration_is_frozen_canonical_and_bound(
    configuration: ProviderExperimentConfiguration, repository_root: Path
) -> None:
    path = repository_root / "configs/experiments/phase13-provider.json"
    assert canonical_configuration_bytes(configuration) == path.read_bytes()
    assert configuration.provider_configuration_fingerprint == (
        "f5dc6fb5b8bf54c7cf1b58b990fa3db44073500df9903e3a7d93cbeb1ad92c2d"
    )
    assert configuration.maximum_call_cost() == Decimal("0.22")
    with pytest.raises(FrozenInstanceError):
        configuration.model = "other"  # type: ignore[misc]


def test_cost_guard_is_fail_closed(configuration: ProviderExperimentConfiguration) -> None:
    guard = CostGuard(configuration)
    assert guard.authorize(Decimal("0"), Decimal("0"), 0) == Decimal("0.22")
    usage = ProviderUsageRecord("archguard.provider-usage/v1", configuration.model, 1000, 400, 200)
    assert guard.observed_cost(usage) == Decimal("0.0046")
    with pytest.raises(ValueError, match="emergency"):
        guard.authorize(Decimal("4.00"), Decimal("0"), 1)
    with pytest.raises(ValueError, match="usage"):
        ProviderUsageRecord("archguard.provider-usage/v1", configuration.model, -1, 0, 0)
    with pytest.raises(ValueError, match="model"):
        ProviderUsageRecord("archguard.provider-usage/v1", "alias", 1, 0, 0)


def test_cost_boundaries_reservations_and_precision(
    configuration: ProviderExperimentConfiguration,
) -> None:
    guard = CostGuard(configuration)
    assert guard.projected_total(Decimal("4.28"), Decimal("0")) == Decimal("4.50")
    assert guard.hard_ceiling_allows(Decimal("4.28"), Decimal("0")) is True
    assert guard.hard_ceiling_allows(Decimal("4.280001"), Decimal("0")) is False
    assert guard.hard_ceiling_allows(Decimal("4.07"), Decimal("0.22")) is False
    assert (
        str(
            guard.observed_cost(
                ProviderUsageRecord("archguard.provider-usage/v1", configuration.model, 1, 0, 1)
            )
        )
        == "0.0000175"
    )


def test_cost_state_accounts_for_retry_and_billed_failure(
    configuration: ProviderExperimentConfiguration,
) -> None:
    guard = CostGuard(configuration)
    state = CostGuardState().reserve(guard)
    assert state.reserved_in_flight_cost_usd == Decimal("0.22")
    failed = ProviderUsageRecord(
        "archguard.provider-usage/v1",
        configuration.model,
        1000,
        0,
        200,
        reasoning_tokens=100,
        request_succeeded=False,
    )
    state = state.record(guard, failed)
    assert state.observed_cost_usd == Decimal("0.0055")
    state = state.reserve(guard, retry=True)
    assert state.attempted_retries == 1
    retry = ProviderUsageRecord(
        "archguard.provider-usage/v1",
        configuration.model,
        100,
        0,
        10,
        attempt_kind="retry",
    )
    state = state.record(guard, retry)
    assert state.completed_primary_executions == 1
    assert state.calls_started == 2


def test_missing_usage_stops_subsequent_calls(
    configuration: ProviderExperimentConfiguration,
) -> None:
    guard = CostGuard(configuration)
    state = CostGuardState().reserve(guard).stop("usage_schema_failure")
    assert state.calls_started == 1
    assert state.reserved_in_flight_cost_usd == 0
    with pytest.raises(ValueError, match="stopped"):
        state.reserve(guard)


def test_usage_schema_and_six_primary_plan(configuration: ProviderExperimentConfiguration) -> None:
    with pytest.raises(ValueError, match="usage"):
        ProviderUsageRecord("archguard.provider-usage/v1", configuration.model, 1, 0, -1)
    with pytest.raises(ValueError, match="reasoning"):
        ProviderUsageRecord(
            "archguard.provider-usage/v1", configuration.model, 1, 0, 1, reasoning_tokens=2
        )
    assert configuration.maximum_call_cost() * 6 == Decimal("1.32")
    assert configuration.maximum_call_cost() * 12 == Decimal("2.64")
    assert configuration.maximum_input_tokens == 40_000
    assert configuration.maximum_output_tokens == 8_000


def test_previous_configuration_and_prospective_amendment_are_immutable(
    repository_root: Path,
) -> None:
    previous_name = (
        "phase13-provider-f7d1586408bdc03aa8243b702211ebc64366558a53d89534f81b0705d31852ce.json"
    )
    previous = json.loads(
        (repository_root / "research/provider-config-history" / previous_name).read_text()
    )
    previous_fingerprint = previous.pop("provider_configuration_fingerprint")
    assert fingerprint(previous) == previous_fingerprint
    amendment = json.loads(
        (repository_root / "research/reviews/phase-13-budget-amendment.json").read_text()
    )
    amendment_fingerprint = amendment.pop("amendment_fingerprint")
    assert fingerprint(amendment) == amendment_fingerprint
    assert amendment["prospective"] is True
    assert amendment["execution_state"]["scientific_executions_observed"] == 0


def test_historical_configuration_identity_does_not_expire(
    configuration: ProviderExperimentConfiguration, repository_root: Path
) -> None:
    path = repository_root / "configs/experiments/phase13-provider.json"
    original = path.read_bytes()
    assert canonical_configuration_bytes(configuration) == original
    assert configuration.provider_configuration_fingerprint == (
        "f5dc6fb5b8bf54c7cf1b58b990fa3db44073500df9903e3a7d93cbeb1ad92c2d"
    )


def test_offline_preflight_requires_secret_and_host(
    configuration: ProviderExperimentConfiguration,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    blocked = provider_preflight(
        configuration, output_directory=tmp_path, analyzed_roots=(tmp_path / "target",)
    )
    assert blocked["status"] == "blocked"
    assert blocked["network_request"] is False
    assert blocked["checks"]["secret_present"] is False
    monkeypatch.setenv("OPENAI_API_KEY", "recognizable-fake-secret")
    monkeypatch.setattr(
        "archguard.infrastructure.provider_preflight.platform.system", lambda: "Linux"
    )
    monkeypatch.setattr(
        "archguard.infrastructure.provider_preflight.platform.machine", lambda: "x86_64"
    )
    monkeypatch.setattr(
        "archguard.infrastructure.provider_preflight.shutil.which", lambda _: "/usr/bin/docker"
    )
    ready = provider_preflight(
        configuration,
        output_directory=tmp_path / "new-output",
        analyzed_roots=(tmp_path / "target",),
        reference_time=datetime(2026, 10, 20, tzinfo=UTC),
    )
    encoded = json.dumps(ready)
    assert ready["status"] == "ready"
    assert "recognizable-fake-secret" not in encoded
    assert "authorization" not in encoded.lower()


@pytest.mark.parametrize(
    ("age", "expected"),
    [
        (timedelta(days=30), True),
        (timedelta(days=30, microseconds=1), False),
    ],
)
def test_live_pricing_freshness_uses_injected_reference_time(
    configuration: ProviderExperimentConfiguration,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    age: timedelta,
    expected: bool,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "recognizable-fake-secret")
    monkeypatch.setattr(
        "archguard.infrastructure.provider_preflight.platform.system", lambda: "Linux"
    )
    monkeypatch.setattr(
        "archguard.infrastructure.provider_preflight.platform.machine", lambda: "x86_64"
    )
    monkeypatch.setattr(
        "archguard.infrastructure.provider_preflight.shutil.which", lambda _: "/usr/bin/docker"
    )
    verified = datetime.fromisoformat(configuration.prices.verified_at.replace("Z", "+00:00"))
    report = provider_preflight(
        configuration,
        output_directory=tmp_path / "output",
        analyzed_roots=(tmp_path / "target",),
        reference_time=verified + age,
    )
    assert report["checks"]["pricing_fresh"] is expected
    assert report["status"] == ("ready" if expected else "blocked")


def test_live_preflight_rejects_naive_reference_time(
    configuration: ProviderExperimentConfiguration, tmp_path: Path
) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        provider_preflight(
            configuration,
            output_directory=tmp_path / "output",
            analyzed_roots=(tmp_path / "target",),
            reference_time=datetime(2026, 10, 20),
        )


def test_live_preflight_rejects_malformed_recorded_pricing_time(
    configuration: ProviderExperimentConfiguration, tmp_path: Path
) -> None:
    malformed = replace(
        configuration,
        prices=replace(configuration.prices, verified_at="not-a-timeZ"),
        provider_configuration_fingerprint="",
    )
    report = provider_preflight(
        malformed,
        output_directory=tmp_path / "output",
        analyzed_roots=(tmp_path / "target",),
        require_secret=False,
        reference_time=datetime(2026, 10, 20, tzinfo=UTC),
    )
    assert report["checks"]["pricing_fresh"] is False
    assert report["status"] == "blocked"


def test_preflight_rejects_output_inside_target(
    configuration: ProviderExperimentConfiguration, tmp_path: Path
) -> None:
    root = tmp_path / "target"
    report = provider_preflight(
        configuration,
        output_directory=root / "results",
        analyzed_roots=(root,),
        require_secret=False,
    )
    assert report["checks"]["output_separate_from_analyzed_roots"] is False
