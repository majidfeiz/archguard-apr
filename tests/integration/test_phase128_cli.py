import json
from pathlib import Path

from typer.testing import CliRunner

from archguard.entrypoints.cli.app import app

runner = CliRunner()


def test_protocol_decision_reports_approved(repository_root: Path) -> None:
    result = runner.invoke(
        app,
        [
            "readiness",
            "decision",
            "validate",
            "--decision",
            str(repository_root / "research/reviews/protocol-decision.json"),
            "--fingerprint",
            "7d43e50dca1be8b2e776bed8d2714000e92e69127bd6c2c46c4a1005bad4f3c1",
        ],
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["approved"] is True


def test_phase13_gate_reports_operational_readiness(repository_root: Path) -> None:
    result = runner.invoke(
        app,
        ["readiness", "gate", "--facts", str(repository_root / "research/readiness-facts.json")],
    )
    assert result.exit_code == 0
    output = json.loads(result.stdout)
    assert output["phase_13_ready"] is True
    assert output["phase_12_complete"] is True
    assert output["phase_13_scientifically_ready"] is True
    assert output["phase_13_operationally_ready"] is True
    assert output["blocker_codes"] == []


def test_phase128a_artifacts_validate(repository_root: Path) -> None:
    result = runner.invoke(
        app,
        ["readiness", "phase128a-validate", "--root", str(repository_root / "research")],
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["artifact_count"] == 6
