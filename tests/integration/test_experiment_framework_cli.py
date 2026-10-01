import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest
from typer.testing import CliRunner

from archguard.application.services.experiments import standard_configurations
from archguard.domain.experiments import CONTRACT_SCHEMA, ComparisonContract
from archguard.domain.orchestration import ArtifactReference
from archguard.entrypoints.cli.app import app

pytestmark = pytest.mark.integration
runner = CliRunner()


def ref(kind: str, char: str) -> ArtifactReference:
    return ArtifactReference(kind, char * 64)


def write_contract(path: Path) -> None:
    value = ComparisonContract(
        CONTRACT_SCHEMA,
        "cli-comparison",
        ref("snapshot", "1"),
        ref("splits", "2"),
        ("task-a",),
        standard_configurations(),
        ref("profiles", "3"),
        2,
        12,
        ("task-a",),
        "no-retry",
        "intent-and-valid",
        "dated-price-table",
        ref("metrics", "4"),
        "linux-x86_64",
        ref("tests", "5"),
    )
    path.write_text(json.dumps(asdict(value)), encoding="utf-8")


def test_plan_contract_schedule_and_acknowledgements(repository_root: Path, tmp_path: Path) -> None:
    plan = repository_root / "configs/experiments/phase12-plan.yaml"
    contract = tmp_path / "contract.json"
    schedule = tmp_path / "schedule.json"
    write_contract(contract)
    assert (
        runner.invoke(app, ["experiment", "plan", "validate", "--plan", str(plan)]).exit_code == 0
    )
    assert (
        runner.invoke(
            app, ["experiment", "compare", "validate", "--contract", str(contract)]
        ).exit_code
        == 0
    )
    created = runner.invoke(
        app,
        [
            "experiment",
            "schedule",
            "create",
            "--plan",
            str(plan),
            "--contract",
            str(contract),
            "--output",
            str(schedule),
        ],
    )
    assert created.exit_code == 0 and json.loads(created.stdout)["run_count"] == 14
    assert (
        runner.invoke(
            app,
            [
                "experiment",
                "schedule",
                "create",
                "--plan",
                str(plan),
                "--contract",
                str(contract),
                "--output",
                str(schedule),
            ],
        ).exit_code
        == 4
    )
    assert (
        runner.invoke(
            app, ["experiment", "run", "--schedule", str(schedule), "--mode", "external-pilot"]
        ).exit_code
        == 5
    )
    assert (
        runner.invoke(
            app, ["experiment", "run", "--schedule", str(schedule), "--mode", "live-pilot"]
        ).exit_code
        == 5
    )
    offline = runner.invoke(
        app, ["experiment", "run", "--schedule", str(schedule), "--mode", "offline"]
    )
    assert offline.exit_code == 0 and json.loads(offline.stdout)["provider_calls_executed"] == 0


def test_offline_fixture_is_byte_identical(repository_root: Path, tmp_path: Path) -> None:
    outputs = (tmp_path / "one", tmp_path / "two")
    for output in outputs:
        subprocess.run(
            [
                sys.executable,
                str(repository_root / "scripts/offline_experiment_demo.py"),
                "--output",
                str(output),
            ],
            check=True,
        )
    names = sorted(path.name for path in outputs[0].iterdir())
    assert names == [
        "blind-mapping.json",
        "comparison.json",
        "ledger.json",
        "results.csv",
        "schedule.json",
        "summary.json",
    ]
    assert all(
        (outputs[0] / name).read_bytes() == (outputs[1] / name).read_bytes() for name in names
    )
    summary = json.loads((outputs[0] / "summary.json").read_text())
    assert summary["missing_count"] > 0 and summary["infrastructure_failure_count"] > 0
    ledger = runner.invoke(
        app, ["experiment", "ledger", "verify", "--ledger", str(outputs[0] / "ledger.json")]
    )
    assert ledger.exit_code == 0 and json.loads(ledger.stdout)["entry_count"] == 56
    status = runner.invoke(
        app,
        ["experiment", "status", "--experiment", str(outputs[0] / "ledger.json")],
    )
    replay = runner.invoke(
        app,
        ["experiment", "resume", "--experiment", str(outputs[0] / "ledger.json")],
    )
    assert status.exit_code == replay.exit_code == 0
    assert json.loads(replay.stdout)["provider_calls_repeated"] == 0
    summary_output = tmp_path / "blinded-summary.json"
    summary_result = runner.invoke(
        app,
        [
            "experiment",
            "summarize",
            "--experiment",
            str(outputs[0] / "ledger.json"),
            "--blinded",
            "--output",
            str(summary_output),
        ],
    )
    assert summary_result.exit_code == 0
    assert "SYSTEM_" in summary_output.read_text()


def test_export_is_deterministic_and_refuses_overwrite(
    repository_root: Path, tmp_path: Path
) -> None:
    experiment = tmp_path / "experiment"
    subprocess.run(
        [
            sys.executable,
            str(repository_root / "scripts/offline_experiment_demo.py"),
            "--output",
            str(experiment),
        ],
        check=True,
    )
    output = tmp_path / "export.csv"
    args = [
        "experiment",
        "export",
        "--experiment",
        str(experiment / "ledger.json"),
        "--format",
        "csv",
        "--output",
        str(output),
    ]
    assert runner.invoke(app, args).exit_code == 0
    assert (
        output.read_text().splitlines()[0]
        == "configuration_id,failure_reason,repetition_id,run_id,status,task_id"
    )
    assert runner.invoke(app, args).exit_code == 4
