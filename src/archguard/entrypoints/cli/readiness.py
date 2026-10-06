"""Phase 12.8 evidence, human-review, and Phase 13 gate commands."""

import json
from pathlib import Path
from typing import Annotated, Never

import typer

from archguard.application.services.readiness import aggregate_readiness, validate_human_decision
from archguard.infrastructure.phase127_evidence import import_phase127_zip, validate_phase127_zip
from archguard.infrastructure.phase128a_artifacts import validate_phase128a_artifacts
from archguard.infrastructure.phase128b_evidence import (
    create_evidence_zip,
    finalize_cleanup,
    import_evidence_zip,
    produce_evidence,
    validate_evidence_zip,
)
from archguard.infrastructure.phase128c_evidence import (
    finalize_cleanup as finalize_phase128c_cleanup,
)
from archguard.infrastructure.phase128c_evidence import (
    import_archive as import_phase128c_archive,
)
from archguard.infrastructure.phase128c_evidence import (
    package as package_phase128c,
)
from archguard.infrastructure.phase128c_evidence import (
    produce as produce_phase128c,
)
from archguard.infrastructure.phase128c_evidence import (
    validate_archive as validate_phase128c_archive,
)
from archguard.infrastructure.readiness_artifacts import load_human_decision, load_json

app = typer.Typer(no_args_is_help=True)
evidence_app = typer.Typer(no_args_is_help=True)
decision_app = typer.Typer(no_args_is_help=True)
phase128b_app = typer.Typer(no_args_is_help=True)
phase128c_app = typer.Typer(no_args_is_help=True)
app.add_typer(evidence_app, name="evidence")
app.add_typer(decision_app, name="decision")
app.add_typer(phase128b_app, name="phase128b")
app.add_typer(phase128c_app, name="phase128c")


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


@phase128b_app.command("produce")
def phase128b_produce(
    external_root: Annotated[Path, typer.Option("--external-root")],
    output: Annotated[Path, typer.Option("--output")],
    repository_root: Annotated[Path, typer.Option("--repository-root")] = Path("."),
    github_run_id: Annotated[str, typer.Option("--github-run-id")] = "local",
    github_job: Annotated[str, typer.Option("--github-job")] = "local",
) -> None:
    """Acquire the authorized pilot and produce source-free evidence."""
    try:
        emit(
            produce_evidence(
                external_root, output, repository_root.resolve(), github_run_id, github_job
            )
        )
    except (OSError, ValueError, json.JSONDecodeError):
        fail("INVALID_PHASE_12_8B_EXECUTION")


@phase128b_app.command("package")
def phase128b_package(
    source: Annotated[Path, typer.Option("--source")],
    archive: Annotated[Path, typer.Option("--archive")],
) -> None:
    try:
        create_evidence_zip(source, archive)
        emit({"status": "packaged", "archive": archive.name})
    except (OSError, ValueError):
        fail("INVALID_PHASE_12_8B_EVIDENCE")


@phase128b_app.command("finalize-cleanup")
def phase128b_finalize_cleanup(
    source: Annotated[Path, typer.Option("--source")],
    external_root: Annotated[Path, typer.Option("--external-root")],
) -> None:
    try:
        emit(finalize_cleanup(source, external_root))
    except (OSError, ValueError):
        fail("INVALID_PHASE_12_8B_CLEANUP")


@phase128b_app.command("validate")
def phase128b_validate(archive: Annotated[Path, typer.Option("--archive")]) -> None:
    try:
        emit({"status": "valid", **validate_evidence_zip(archive)})
    except (OSError, ValueError, KeyError):
        fail("INVALID_PHASE_12_8B_EVIDENCE")


@phase128b_app.command("import")
def phase128b_import(
    archive: Annotated[Path, typer.Option("--archive")],
    output: Annotated[Path, typer.Option("--output")],
) -> None:
    try:
        emit({"status": "imported", **import_evidence_zip(archive, output)})
    except (OSError, ValueError, KeyError):
        fail("INVALID_PHASE_12_8B_EVIDENCE")


@phase128c_app.command("produce")
def phase128c_produce(
    external_root: Annotated[Path, typer.Option("--external-root")],
    output: Annotated[Path, typer.Option("--output")],
    repository_root: Annotated[Path, typer.Option("--repository-root")] = Path("."),
    github_run_id: Annotated[str, typer.Option("--github-run-id")] = "local",
) -> None:
    try:
        emit(produce_phase128c(external_root, output, repository_root, github_run_id))
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        fail("INVALID_PHASE_12_8C_EXECUTION")


@phase128c_app.command("finalize-cleanup")
def phase128c_finalize_cleanup(
    source: Annotated[Path, typer.Option("--source")],
    external_root: Annotated[Path, typer.Option("--external-root")],
) -> None:
    try:
        finalize_phase128c_cleanup(source, external_root)
        emit({"status": "complete"})
    except (OSError, ValueError):
        fail("INVALID_PHASE_12_8C_CLEANUP")


@phase128c_app.command("package")
def phase128c_package(
    source: Annotated[Path, typer.Option("--source")],
    archive: Annotated[Path, typer.Option("--archive")],
) -> None:
    try:
        package_phase128c(source, archive)
        emit({"status": "packaged", "archive": archive.name})
    except (OSError, ValueError):
        fail("INVALID_PHASE_12_8C_EVIDENCE")


@phase128c_app.command("validate")
def phase128c_validate(archive: Annotated[Path, typer.Option("--archive")]) -> None:
    try:
        emit({"status": "valid", **validate_phase128c_archive(archive)})
    except (OSError, ValueError, KeyError):
        fail("INVALID_PHASE_12_8C_EVIDENCE")


@phase128c_app.command("import")
def phase128c_import(
    archive: Annotated[Path, typer.Option("--archive")],
    output: Annotated[Path, typer.Option("--output")],
) -> None:
    try:
        emit({"status": "imported", **import_phase128c_archive(archive, output)})
    except (OSError, ValueError, KeyError):
        fail("INVALID_PHASE_12_8C_EVIDENCE")
