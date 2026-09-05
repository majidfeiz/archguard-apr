import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from archguard.entrypoints.cli.app import app
from tests.unit.test_repository_analysis import write

pytestmark = pytest.mark.integration
runner = CliRunner()


def test_analyze_and_inspect(tmp_path: Path) -> None:
    root = tmp_path / "source"
    write(root, "src/example/a.py")
    result = runner.invoke(app, ["repository", "analyze", str(root), "--source-root", "src"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["status"] == "complete"
    assert str(root) not in result.stdout
    assert not list(root.glob("*.json"))
    output = tmp_path / "output.json"
    result = runner.invoke(app, ["repository", "analyze", str(root), "--output", str(output)])
    assert result.exit_code == 0, result.output
    sha = json.loads(result.stdout)["artifact_sha256"]
    inspected = runner.invoke(app, ["repository", "inspect", str(output), "--sha256", sha])
    assert inspected.exit_code == 0, inspected.output
    assert json.loads(inspected.stdout)["summary"]["parsed_files"] == 1


def test_partial_strict_and_fail_fast(tmp_path: Path) -> None:
    root = tmp_path / "source"
    write(root, "bad.py", b"def bad(\n")
    args = ["repository", "analyze", str(root)]
    result = runner.invoke(app, args)
    assert result.exit_code == 0
    assert json.loads(result.stdout)["status"] == "partial"
    output = tmp_path / "partial.json"
    result = runner.invoke(app, args + ["--strict", "--output", str(output)])
    assert result.exit_code == 1
    assert output.exists()
    config = tmp_path / "app.yaml"
    config.write_text("analysis:\n  fail_fast: true\n")
    result = runner.invoke(app, args + ["--config", str(config)])
    assert result.exit_code == 1


def test_invalid_roots_and_outputs(tmp_path: Path) -> None:
    root = tmp_path / "source"
    write(root, "a.py")
    args = ["repository", "analyze", str(root)]
    assert runner.invoke(app, ["repository", "analyze", str(tmp_path / "missing")]).exit_code == 2
    result = runner.invoke(app, args + ["--output", str(root / "out.json")])
    assert result.exit_code == 3
    assert str(root) not in result.output
    assert runner.invoke(app, args + ["--source-root", "../src"]).exit_code == 2


@pytest.mark.parametrize("data", ["{", '{"schema_version":"2"}', "null"])
def test_inspect_bad_json(tmp_path: Path, data: str) -> None:
    path = write(tmp_path, "artifact.json", data.encode())
    result = runner.invoke(app, ["repository", "inspect", str(path)])
    assert result.exit_code == 2
    assert str(tmp_path) not in result.output


def test_io_error(tmp_path: Path) -> None:
    root = tmp_path / "source"
    write(root, "a.py")
    with patch("archguard.infrastructure.artifact_io.os.replace", side_effect=OSError):
        result = runner.invoke(
            app, ["repository", "analyze", str(root), "--output", str(tmp_path / "a.json")]
        )
    assert result.exit_code == 1


def test_config_environment_and_strict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from archguard.infrastructure.config import load_settings

    config = tmp_path / "app.yaml"
    config.write_text("analysis:\n  max_file_bytes: 20\n  source_roots: [src]\n  strict: true\n")
    monkeypatch.setenv("ARCHGUARD_ANALYSIS__MAX_FILE_BYTES", "30")
    settings = load_settings(config)
    assert settings.analysis.max_file_bytes == 30
    assert settings.analysis.source_roots == ("src",)
    root = tmp_path / "source"
    write(root, "a.py", b"#" * 100)
    result = runner.invoke(app, ["repository", "analyze", str(root), "--config", str(config)])
    assert result.exit_code == 1
