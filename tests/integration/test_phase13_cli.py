import json
import shutil
from decimal import Decimal
from pathlib import Path

import pytest
from typer.testing import CliRunner

from archguard.application.ports.phase13 import TreatmentRequest
from archguard.domain.phase13 import ProviderUsage
from archguard.entrypoints.cli.app import app
from archguard.infrastructure.phase13_live import Phase13LiveExecutor
from archguard.infrastructure.provider_preflight import load_phase13_provider_configuration


def _arguments(repository_root: Path, output: Path) -> list[str]:
    return [
        "experiment",
        "run-frozen",
        "--population",
        str(repository_root / "research/population/exploratory-feasibility-v1.json"),
        "--protocol",
        str(repository_root / "research/protocol/exploratory-feasibility-v2.json"),
        "--provider-config",
        str(repository_root / "configs/experiments/phase13-provider.json"),
        "--output",
        str(output),
    ]


def test_frozen_cli_without_acknowledgements_is_offline(
    repository_root: Path, tmp_path: Path
) -> None:
    output = tmp_path / "evidence"
    result = CliRunner().invoke(app, _arguments(repository_root, output))
    assert result.exit_code == 5
    assert not output.exists()
    assert json.loads(result.stdout)["diagnostic_code"] == (
        "frozen_experiment_requires_both_acknowledgements"
    )


def test_resume_cli_reaches_black4_ordinals_five_then_six_without_network(
    repository_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "evidence"
    owned = tmp_path / "owned"
    provider_ordinals: list[int] = []

    class OfflineBoundaryExecutor(Phase13LiveExecutor):
        def __init__(self, root: Path, provider_config: Path, protocol_fingerprint: str) -> None:
            self.repository_root = repository_root.resolve()
            self.configuration = load_phase13_provider_configuration(provider_config)
            self.protocol_fingerprint = protocol_fingerprint
            self.root = owned
            self.root.mkdir()
            self._owned = []

        def _checkout(self, request: TreatmentRequest, destination: Path) -> None:
            assert request.identity.ordinal in (5, 6)
            destination.mkdir(parents=True)
            (destination / "sample.py").write_text("VALUE = 1\n")

        def _context(self, request: TreatmentRequest, source: Path) -> tuple[str, str]:
            return "source-free fake context", "a" * 64

        def _invoke(
            self, request: TreatmentRequest, context: str
        ) -> tuple[str, str, ProviderUsage]:
            state = json.loads((output / "cost-state.json").read_text())
            expected_carried = 4 + len(provider_ordinals)
            assert state["completed_primary"] == expected_carried
            assert state["provider_calls_started"] == expected_carried
            assert state["provider_calls_completed"] == expected_carried
            assert state["provider_calls_with_usage"] == expected_carried
            if not provider_ordinals:
                assert state["observed_usd"] == "0.1296325"
            assert state["stop_reason"] == "running"
            provider_ordinals.append(request.identity.ordinal)
            return "not a diff", "d" * 64, ProviderUsage(10, 0, 5, 0)

        def cleanup(self) -> bool:
            shutil.rmtree(self.root, ignore_errors=True)
            return True

    monkeypatch.setattr(
        "archguard.entrypoints.cli.experiment.Phase13LiveExecutor", OfflineBoundaryExecutor
    )
    arguments = [
        *_arguments(repository_root, output),
        "--resume-checkpoint",
        str(repository_root / "research/evidence/phase-13-checkpoint-four-executions.json"),
        "--acknowledge-provider-cost",
        "--acknowledge-source-processing",
    ]
    result = CliRunner().invoke(app, arguments)
    assert result.exit_code == 0, result.stdout
    assert provider_ordinals == [5, 6]
    assert json.loads(result.stdout) == {
        "completed_primary_executions": 6,
        "provider_calls_executed": 2,
        "status": "complete",
    }
    checkpoint = json.loads(
        (repository_root / "research/evidence/phase-13-checkpoint-four-executions.json").read_text()
    )
    carried = [json.loads((output / f"execution-{n}.json").read_text()) for n in range(1, 5)]
    assert carried == checkpoint["completed_executions"]
    assert (
        json.loads((output / "execution-5.json").read_text())["terminal_classification"]
        == "invalid_patch"
    )
    assert (
        json.loads((output / "execution-6.json").read_text())["terminal_classification"]
        == "invalid_patch"
    )
    state = json.loads((output / "cost-state.json").read_text())
    assert state["completed_primary"] == 6
    assert state["provider_calls_started"] == 6
    assert Decimal(state["observed_usd"]) > Decimal("0.1296325")
