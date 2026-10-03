import json
from pathlib import Path

from typer.testing import CliRunner

from archguard.entrypoints.cli.app import app

runner = CliRunner()


def test_pending_decision_reports_not_approved(repository_root: Path) -> None:
    result = runner.invoke(
        app,
        [
            "readiness",
            "decision",
            "validate",
            "--decision",
            str(repository_root / "research/reviews/protocol-decision.json"),
            "--fingerprint",
            "921a3ffa97e866b9ce7aa3431463ab6e8efbf41814a223ffe040e978a44dd0d9",
        ],
    )
    assert result.exit_code == 3
    assert json.loads(result.stdout)["approved"] is False


def test_phase13_gate_reports_all_current_blockers(repository_root: Path) -> None:
    result = runner.invoke(
        app,
        ["readiness", "gate", "--facts", str(repository_root / "research/readiness-facts.json")],
    )
    assert result.exit_code == 4
    output = json.loads(result.stdout)
    assert output["phase_13_ready"] is False
    assert "PROFILE_REVIEW_REQUIRED" in output["blocker_codes"]
