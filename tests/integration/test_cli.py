import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from archguard.entrypoints.cli.app import app

pytestmark = pytest.mark.integration
runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "0.11.0"


def test_config() -> None:
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["provider_execution_enabled"] is False


def test_doctor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("archguard.entrypoints.cli.app.shutil.which", lambda name: "/bin/" + name)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["configuration_valid"]


def test_missing_docker_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "archguard.entrypoints.cli.app.shutil.which",
        lambda name: None if name == "docker" else "/bin/git",
    )
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert not json.loads(result.stdout)["docker_executable_available"]


def test_doctor_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARCHGUARD_WORKSPACE_DIR", "/nonexistent/archguard-test")
    assert runner.invoke(app, ["doctor"]).exit_code == 1


@pytest.mark.parametrize("command", [["doctor"], ["config", "show"]])
def test_invalid_config(command: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARCHGUARD_EXECUTION_TIMEOUT", "token=private-value")
    result = runner.invoke(app, command)
    assert result.exit_code == 2
    assert "private-value" not in result.output
    assert "execution_timeout" in result.output


def test_experiment(repository_root: Path, tmp_path: Path) -> None:
    before = set(tmp_path.iterdir())
    result = runner.invoke(
        app,
        [
            "experiment",
            "validate",
            "--config",
            str(repository_root / "configs/experiments/smoke.yaml"),
        ],
    )
    assert result.exit_code == 0
    assert set(tmp_path.iterdir()) == before
    assert json.loads(result.stdout)["experiment_name"] == "foundation-smoke"


@pytest.mark.parametrize("content", ["schema_version: '9'", "[", "[]"])
def test_invalid_experiment(tmp_path: Path, content: str) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(content)
    assert runner.invoke(app, ["experiment", "validate", "--config", str(path)]).exit_code == 2


def test_missing_file() -> None:
    assert runner.invoke(app, ["experiment", "validate", "--config", "missing.yaml"]).exit_code == 2


def test_config_yaml(repository_root: Path) -> None:
    assert (
        runner.invoke(
            app, ["config", "show", "--config", str(repository_root / "configs/app.example.yaml")]
        ).exit_code
        == 0
    )
