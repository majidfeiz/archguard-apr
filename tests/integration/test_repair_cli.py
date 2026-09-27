import json
from pathlib import Path

from typer.testing import CliRunner

from archguard.entrypoints.cli.app import app


def test_start_status_replay_and_immutable_output(repository_root: Path, tmp_path: Path) -> None:
    spec = repository_root / "examples/repair/run-spec.yaml"
    run = tmp_path / "run"
    runner = CliRunner()
    started = runner.invoke(
        app, ["repair", "run", "start", "--spec", str(spec), "--output", str(run)]
    )
    assert started.exit_code == 0
    assert json.loads(started.stdout)["state"] == "created"
    status = runner.invoke(app, ["repair", "run", "status", "--run", str(run)])
    assert status.exit_code == 0
    assert json.loads(status.stdout)["event_count"] == 1
    replayed = runner.invoke(app, ["repair", "run", "replay", "--run", str(run)])
    assert replayed.exit_code == 0
    assert json.loads(replayed.stdout)["agent_invocations"] == 0
    repeated = runner.invoke(
        app, ["repair", "run", "start", "--spec", str(spec), "--output", str(run)]
    )
    assert repeated.exit_code == 2


def test_replay_rejects_tampered_event_log(repository_root: Path, tmp_path: Path) -> None:
    run = tmp_path / "run"
    runner = CliRunner()
    runner.invoke(
        app,
        [
            "repair",
            "run",
            "start",
            "--spec",
            str(repository_root / "examples/repair/run-spec.yaml"),
            "--output",
            str(run),
        ],
    )
    (run / "events.json").write_text("[]\n")
    result = runner.invoke(app, ["repair", "run", "replay", "--run", str(run)])
    assert result.exit_code == 7
