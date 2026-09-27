import json
from pathlib import Path

from typer.testing import CliRunner

from archguard.entrypoints.cli.app import app


def test_execution_plan_validate_and_inspect(repository_root: Path) -> None:
    plan = repository_root / "examples/execution/archguard-self.yaml"
    runner = CliRunner()
    validated = runner.invoke(app, ["execution", "plan", "validate", "--plan", str(plan)])
    assert validated.exit_code == 0
    assert json.loads(validated.stdout)["status"] == "valid"
    inspected = runner.invoke(app, ["execution", "plan", "inspect", "--plan", str(plan)])
    assert inspected.exit_code == 0
    assert json.loads(inspected.stdout)["stage_ids"] == ["tests"]


def test_execution_plan_rejects_mutable_image(tmp_path: Path) -> None:
    plan = tmp_path / "bad.yaml"
    plan.write_text("schema: archguard.execution-plan/v1\nplan_id: bad\nimage: python:latest\n")
    result = CliRunner().invoke(app, ["execution", "plan", "validate", "--plan", str(plan)])
    assert result.exit_code == 2
    assert json.loads(result.stdout)["diagnostic_code"] == "invalid_execution_plan"
