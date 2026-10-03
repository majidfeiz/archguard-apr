"""Phase 12.8 evidence, human-review, and Phase 13 gate commands."""

import json
from pathlib import Path
from typing import Annotated, Never

import typer

from archguard.application.services.readiness import aggregate_readiness, validate_human_decision
from archguard.infrastructure.phase127_evidence import import_phase127_zip, validate_phase127_zip
from archguard.infrastructure.phase128a_artifacts import validate_phase128a_artifacts
from archguard.infrastructure.readiness_artifacts import load_human_decision, load_json

app = typer.Typer(no_args_is_help=True)
evidence_app = typer.Typer(no_args_is_help=True)
decision_app = typer.Typer(no_args_is_help=True)
app.add_typer(evidence_app, name="evidence")
app.add_typer(decision_app, name="decision")


def emit(value: object) -> None:
    typer.echo(json.dumps(value, sort_keys=True, separators=(",", ":")))


def fail(diagnostic: str) -> Never:
    emit({"diagnostic_code": diagnostic, "status": "error"})
    raise typer.Exit(2)


@evidence_app.command("validate")
def evidence_validate(archive: Annotated[Path, typer.Option("--archive")]) -> None:
    try:
        value = validate_phase127_zip(archive)
    except (OSError, ValueError, KeyError):
        fail("INVALID_PHASE_12_7_EVIDENCE")
    emit({"status": "valid", "fingerprint": value.fingerprint, "task_id": value.task_id})


@evidence_app.command("import")
def evidence_import(
    archive: Annotated[Path, typer.Option("--archive")],
    output: Annotated[Path, typer.Option("--output")],
) -> None:
    try:
        value = import_phase127_zip(archive, output)
    except (OSError, ValueError, KeyError):
        fail("INVALID_PHASE_12_7_EVIDENCE")
    emit({"status": "imported", "fingerprint": value.fingerprint})


@decision_app.command("validate")
def decision_validate(
    decision: Annotated[Path, typer.Option("--decision")],
    fingerprint: Annotated[str, typer.Option("--fingerprint")],
) -> None:
    try:
        value = load_human_decision(decision)
        result = validate_human_decision(value, fingerprint)
    except (OSError, ValueError):
        fail("INVALID_HUMAN_DECISION")
    emit(result)
    if not result["approved"]:
        raise typer.Exit(3)


@app.command("gate")
def gate(facts: Annotated[Path, typer.Option("--facts")]) -> None:
    try:
        result = aggregate_readiness(load_json(facts))
    except (OSError, ValueError):
        fail("INVALID_READINESS_FACTS")
    emit(result)
    if not result["phase_13_ready"]:
        raise typer.Exit(4)


@app.command("phase128a-validate")
def phase128a_validate(root: Annotated[Path, typer.Option("--root")] = Path("research")) -> None:
    """Validate source-free Phase 12.8A artifacts without external execution."""
    try:
        emit(validate_phase128a_artifacts(root))
    except (OSError, ValueError, json.JSONDecodeError):
        fail("INVALID_PHASE_12_8A_ARTIFACT")
