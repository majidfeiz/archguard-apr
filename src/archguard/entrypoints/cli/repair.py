"""Provider-neutral repair-run CLI; outputs references and summaries only."""

from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Never

import typer

from archguard.application.services.orchestration import DeterministicCoordinator, replay, resume
from archguard.domain.orchestration import (
    HUMAN_DECISION_SCHEMA,
    HumanDecision,
    HumanDecisionKind,
    RepairCheckpoint,
    RepairRunSpec,
    RunEvent,
)
from archguard.entrypoints.cli.graph import emit
from archguard.infrastructure.orchestration import LocalRunArtifacts

app = typer.Typer(no_args_is_help=True)
run_app = typer.Typer(no_args_is_help=True)
candidate_app = typer.Typer(no_args_is_help=True)
decision_app = typer.Typer(no_args_is_help=True)
app.add_typer(run_app, name="run")
app.add_typer(candidate_app, name="candidate")
app.add_typer(decision_app, name="decision")


def fail(code: int, diagnostic: str) -> Never:
    emit({"diagnostic_code": diagnostic, "status": "error"})
    raise typer.Exit(code)


@run_app.command("validate")
def validate(spec: Annotated[Path, typer.Option("--spec")]) -> None:
    try:
        value = LocalRunArtifacts().load_spec(spec)
        emit(
            {"status": "valid", "run_id": value.run_id, "spec_fingerprint": value.spec_fingerprint}
        )
    except (ValueError, OSError):
        fail(2, "invalid_run_specification")


@run_app.command("start")
def start(
    spec: Annotated[Path, typer.Option("--spec")], output: Annotated[Path, typer.Option("--output")]
) -> None:
    try:
        value = LocalRunArtifacts().load_spec(spec)
        coordinator = DeterministicCoordinator()
        snapshot, events = coordinator.create(value)
        checkpoint = coordinator.checkpoint(value, snapshot, events)
        LocalRunArtifacts().write_run(output, value, events, checkpoint)
        emit(
            {
                "run_id": value.run_id,
                "state": snapshot.state,
                "checkpoint_fingerprint": checkpoint.checkpoint_fingerprint,
                "next_action": "resume",
            }
        )
    except FileExistsError:
        fail(2, "run_output_exists")
    except (ValueError, OSError):
        fail(2, "invalid_run_input")


def loaded(directory: Path) -> tuple[RepairRunSpec, tuple[RunEvent, ...], RepairCheckpoint]:
    try:
        return LocalRunArtifacts().read_run(directory)
    except (ValueError, OSError):
        fail(7, "run_integrity_failure")


@run_app.command("status")
def status(run: Annotated[Path, typer.Option("--run")]) -> None:
    spec, events, checkpoint = loaded(run)
    snapshot = resume(spec, events, checkpoint)
    emit(
        {
            "run_id": spec.run_id,
            "state": snapshot.state,
            "selected_candidate_id": snapshot.selected_candidate_id,
            "pending_human_decision": snapshot.pending_human_decision,
            "event_count": len(events),
        }
    )


@run_app.command("events")
def events(run: Annotated[Path, typer.Option("--run")]) -> None:
    spec, values, checkpoint = loaded(run)
    resume(spec, values, checkpoint)
    emit({"events": [asdict(item) for item in values]})


@run_app.command("candidates")
def candidates(run: Annotated[Path, typer.Option("--run")]) -> None:
    spec, events, checkpoint = loaded(run)
    snapshot = resume(spec, events, checkpoint)
    emit({"candidates": [asdict(item) for item in snapshot.candidates]})


@run_app.command("replay")
def replay_run(run: Annotated[Path, typer.Option("--run")]) -> None:
    spec, events, checkpoint = loaded(run)
    try:
        resume(spec, events, checkpoint)
        state = replay(spec, events)
    except ValueError:
        fail(7, "run_integrity_failure")
    if state != checkpoint.state:
        fail(7, "replay_state_mismatch")
    emit(
        {
            "run_id": spec.run_id,
            "state": state,
            "event_chain_fingerprint": checkpoint.event_chain_fingerprint,
            "agent_invocations": 0,
            "executions": 0,
        }
    )


@run_app.command("resume")
def resume_run(run: Annotated[Path, typer.Option("--run")]) -> None:
    spec, events, checkpoint = loaded(run)
    snapshot = resume(spec, events, checkpoint)
    emit({"run_id": spec.run_id, "state": snapshot.state, "next_action": "coordinator_required"})


@candidate_app.command("inspect")
def inspect_candidate(
    run: Annotated[Path, typer.Option("--run")],
    candidate: Annotated[str, typer.Option("--candidate")],
) -> None:
    spec, events, checkpoint = loaded(run)
    snapshot = resume(spec, events, checkpoint)
    value = next((item for item in snapshot.candidates if item.candidate_id == candidate), None)
    if value is None:
        fail(2, "unknown_candidate")
    emit(asdict(value))


@decision_app.command("record")
def record_decision(
    run: Annotated[Path, typer.Option("--run")],
    candidate: Annotated[str, typer.Option("--candidate")],
    decision: Annotated[HumanDecisionKind, typer.Option("--decision")],
) -> None:
    spec, events, checkpoint = loaded(run)
    snapshot = resume(spec, events, checkpoint)
    if not snapshot.pending_human_decision or snapshot.selected_candidate_id != candidate:
        fail(2, "stale_or_unexpected_human_decision")
    try:
        LocalRunArtifacts().write_decision(
            run,
            HumanDecision(
                HUMAN_DECISION_SCHEMA,
                spec.run_id,
                candidate,
                checkpoint.checkpoint_fingerprint,
                decision,
            ),
        )
    except FileExistsError:
        fail(2, "human_decision_exists")
    emit({"status": "recorded", "decision": decision})
