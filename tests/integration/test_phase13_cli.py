import json
from pathlib import Path

from typer.testing import CliRunner

from archguard.entrypoints.cli.app import app


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
