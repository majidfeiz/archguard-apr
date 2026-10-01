import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from archguard.entrypoints.cli.app import app
from archguard.infrastructure.benchmark import CACHE_MARKER

pytestmark = pytest.mark.integration
runner = CliRunner()


def test_registry_validate_and_inspect(repository_root: Path) -> None:
    registry = repository_root / "configs/benchmarks.fixture.yaml"
    validated = runner.invoke(
        app, ["benchmark", "registry", "validate", "--registry", str(registry)]
    )
    inspected = runner.invoke(
        app, ["benchmark", "registry", "inspect", "--registry", str(registry)]
    )
    assert validated.exit_code == inspected.exit_code == 0
    assert json.loads(validated.stdout)["network_access"] is False
    assert json.loads(inspected.stdout)["benchmarks"][0]["benchmark_id"] == "synthetic-fixture"


def test_cache_verify_and_corruption(tmp_path: Path) -> None:
    payload = tmp_path / "metadata.json"
    payload.write_text("{}", encoding="utf-8")
    marker = {
        "schema": "archguard.benchmark-cache/v1",
        "files": [{"path": payload.name, "sha256": hashlib.sha256(b"{}").hexdigest()}],
    }
    (tmp_path / CACHE_MARKER).write_text(json.dumps(marker), encoding="utf-8")
    assert (
        runner.invoke(app, ["benchmark", "cache", "verify", "--cache", str(tmp_path)]).exit_code
        == 0
    )
    payload.write_text("altered", encoding="utf-8")
    result = runner.invoke(app, ["benchmark", "cache", "verify", "--cache", str(tmp_path)])
    assert result.exit_code == 3
    assert "invalid_benchmark_cache" in result.stdout


def test_acquisition_is_explicit_and_never_implicit(repository_root: Path, tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "benchmark",
            "acquire",
            "--registry",
            str(repository_root / "configs/benchmarks.fixture.yaml"),
            "--cache",
            str(tmp_path / "new-cache"),
        ],
    )
    assert result.exit_code == 4
    assert json.loads(result.stdout)["network_required"] is True
