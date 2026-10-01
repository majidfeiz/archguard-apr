import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from archguard.entrypoints.cli.app import app

pytestmark = pytest.mark.integration
runner = CliRunner()


def test_external_preflight_is_offline_and_reports_arm(
    repository_root: Path, tmp_path: Path
) -> None:
    output = tmp_path / "preflight.json"
    result = runner.invoke(
        app,
        [
            "benchmark",
            "external",
            "preflight",
            "--registry",
            str(repository_root / "configs/benchmarks.external-metadata.yaml"),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0
    value = json.loads(result.stdout)
    assert value["network_access"] is False and value["paid_provider_calls"] == 0
    assert output.read_bytes().endswith(b"\n")
    assert (
        runner.invoke(
            app,
            [
                "benchmark",
                "external",
                "preflight",
                "--registry",
                str(repository_root / "configs/benchmarks.external-metadata.yaml"),
                "--output",
                str(output),
            ],
        ).exit_code
        == 4
    )


def test_acquisition_requires_ack_and_external_destination(
    repository_root: Path, tmp_path: Path
) -> None:
    registry = repository_root / "configs/benchmarks.external-metadata.yaml"
    base = [
        "benchmark",
        "external",
        "acquire",
        "--registry",
        str(registry),
        "--cache",
        str(tmp_path / "cache"),
        "--repository",
        str(repository_root),
    ]
    assert runner.invoke(app, base).exit_code == 5
    inside = [
        "benchmark",
        "external",
        "acquire",
        "--registry",
        str(registry),
        "--cache",
        str(repository_root / "cache"),
        "--repository",
        str(repository_root),
        "--acknowledge-network",
    ]
    assert runner.invoke(app, inside).exit_code == 2
    accepted = runner.invoke(app, [*base, "--acknowledge-network"])
    assert accepted.exit_code == 0 and json.loads(accepted.stdout)["adapter_required"] is True
