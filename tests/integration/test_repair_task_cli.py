import json
from pathlib import Path

from typer.testing import CliRunner

from archguard.entrypoints.cli.app import app


def test_repair_task_validate_and_inspect(repository_root: Path) -> None:
    runner = CliRunner()
    path = repository_root / "examples/repair/task.yaml"
    validated = runner.invoke(app, ["repair", "task", "validate", "--task", str(path)])
    assert validated.exit_code == 0, validated.output
    assert json.loads(validated.stdout)["status"] == "valid"
    inspected = runner.invoke(app, ["repair", "task", "inspect", "--task", str(path)])
    assert inspected.exit_code == 0
    output = json.loads(inspected.stdout)
    assert output["maximum_rounds"] == 3
    assert "problem_statement" not in output


def test_repair_task_rejects_invalid(tmp_path: Path) -> None:
    path = tmp_path / "task.yaml"
    path.write_text("schema: bad\n")
    result = CliRunner().invoke(app, ["repair", "task", "validate", "--task", str(path)])
    assert result.exit_code == 2
    assert "invalid_repair_task" in result.stdout
