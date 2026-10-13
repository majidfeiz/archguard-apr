import json
import shutil
from decimal import Decimal
from pathlib import Path

import pytest
from typer.testing import CliRunner

from archguard.application.ports.phase13 import PreProviderFailure, TreatmentRequest
from archguard.domain.phase13 import (
    PreProviderDiagnostic,
    PreProviderExceptionCategory,
    PreProviderStage,
    ProviderUsage,
)
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


def test_resume_cli_reaches_ordinal_two_provider_boundary_once_without_network(
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
            if request.identity.ordinal == 3:
                raise PreProviderFailure(
                    PreProviderDiagnostic(
                        3,
                        request.identity.task_id,
                        request.identity.condition,
                        PreProviderStage.CHECKOUT,
                        PreProviderExceptionCategory.VALIDATION_FAILURE,
                    )
                )
            assert request.identity.ordinal == 2
            destination.mkdir(parents=True)
            (destination / "sample.py").write_text("VALUE = 1\n")

        def _invoke(
            self, request: TreatmentRequest, context: str
        ) -> tuple[str, str, ProviderUsage]:
            state = json.loads((output / "cost-state.json").read_text())
            assert state["completed_primary"] == 1
            assert state["provider_calls_started"] == 1
            assert state["provider_calls_completed"] == 1
            assert state["provider_calls_with_usage"] == 1
            assert state["observed_usd"] == "0.025945"
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
        str(repository_root / "research/evidence/phase-13-checkpoint-run-38452767198.json"),
        "--acknowledge-provider-cost",
        "--acknowledge-source-processing",
    ]
    result = CliRunner().invoke(app, arguments)
    assert result.exit_code == 0, result.stdout
    assert provider_ordinals == [2]
    assert json.loads(result.stdout) == {
        "completed_primary_executions": 2,
        "provider_calls_executed": 1,
        "status": "partial",
    }
    carried = json.loads((output / "execution-1.json").read_text())
    checkpoint = json.loads(
        (repository_root / "research/evidence/phase-13-checkpoint-run-38452767198.json").read_text()
    )
    assert carried == checkpoint["completed_executions"][0]
    ordinal_two = json.loads((output / "execution-2.json").read_text())
    assert ordinal_two["terminal_classification"] == "invalid_patch"
    state = json.loads((output / "cost-state.json").read_text())
    assert state["completed_primary"] == 2
    assert state["provider_calls_started"] == 2
    assert Decimal(state["observed_usd"]) > Decimal("0.025945")
    diagnostic = json.loads((output / "pre-provider-failure.json").read_text())
    assert set(diagnostic) == {
        "run_ordinal",
        "task_id",
        "condition",
        "stage",
        "exception_category",
        "diagnostic_fingerprint",
    }
    assert diagnostic["run_ordinal"] == 3
    assert diagnostic["stage"] == "checkout"
