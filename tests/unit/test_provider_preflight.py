import json
from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path

import pytest

from archguard.domain.provider_preflight import (
    CostGuard,
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
        "f7d1586408bdc03aa8243b702211ebc64366558a53d89534f81b0705d31852ce"
    )
    assert configuration.maximum_call_cost() == Decimal("0.22")
    with pytest.raises(FrozenInstanceError):
        configuration.model = "other"  # type: ignore[misc]


def test_cost_guard_is_fail_closed(configuration: ProviderExperimentConfiguration) -> None:
    guard = CostGuard(configuration)
    assert guard.authorize(Decimal("0"), 0) == Decimal("0.22")
    usage = ProviderUsageRecord("archguard.provider-usage/v1", configuration.model, 1000, 400, 200)
    assert guard.observed_cost(usage) == Decimal("0.0046")
    with pytest.raises(ValueError, match="emergency"):
        guard.authorize(Decimal("15"), 1)
    with pytest.raises(ValueError, match="usage"):
        ProviderUsageRecord("archguard.provider-usage/v1", configuration.model, -1, 0, 0)
    with pytest.raises(ValueError, match="model"):
        ProviderUsageRecord("archguard.provider-usage/v1", "alias", 1, 0, 0)


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
    )
    encoded = json.dumps(ready)
    assert ready["status"] == "ready"
    assert "recognizable-fake-secret" not in encoded
    assert "authorization" not in encoded.lower()


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
