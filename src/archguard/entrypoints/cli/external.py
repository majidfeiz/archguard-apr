"""Fail-closed external benchmark readiness commands."""

import json
import platform
from pathlib import Path
from typing import Annotated, Never

import typer

from archguard.domain.external_readiness import ExternalReadiness, ProfileReviewDecision
from archguard.infrastructure.experiment_artifacts import load_experiment_artifact
from archguard.infrastructure.external_storage import validate_external_root

app = typer.Typer(no_args_is_help=True)
licenses_app = typer.Typer(no_args_is_help=True)
profile_app = typer.Typer(no_args_is_help=True)
pilot_app = typer.Typer(no_args_is_help=True)
evaluator_app = typer.Typer(no_args_is_help=True)
app.add_typer(licenses_app, name="licenses")
app.add_typer(profile_app, name="profile")
app.add_typer(pilot_app, name="pilot")
app.add_typer(evaluator_app, name="evaluator")


def emit(value: object) -> None:
    typer.echo(json.dumps(value, sort_keys=True, separators=(",", ":")))


def fail(code: int, diagnostic: str) -> Never:
    emit({"diagnostic_code": diagnostic, "status": "error"})
    raise typer.Exit(code)


@app.command("preflight")
def preflight(
    registry: Annotated[Path, typer.Option("--registry")],
    output: Annotated[Path, typer.Option("--output")],
) -> None:
    if output.exists():
        fail(4, "immutable_output_exists")
    try:
        raw = registry.read_text(encoding="utf-8")
        if "bugsinpy" not in raw.lower() or "swe-bench" not in raw.lower():
            raise ValueError("missing official benchmark metadata")
        value = {
            "schema": "archguard.external-preflight/v1",
            "network_access": False,
            "host_architecture": platform.machine(),
            "linux_x86_final_ready": platform.system() == "Linux"
            and platform.machine() == "x86_64",
            "paid_provider_calls": 0,
            "next_step": "human review and controlled external qualification",
        }
        output.write_text(
            json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
        )
    except (OSError, ValueError):
        fail(2, "invalid_external_registry")
    emit(value)


@app.command("acquire")
def acquire(
    registry: Annotated[Path, typer.Option("--registry")],
    cache: Annotated[Path, typer.Option("--cache")],
    repository: Annotated[Path, typer.Option("--repository")],
    acknowledge_network: Annotated[bool, typer.Option("--acknowledge-network")] = False,
) -> None:
    if not acknowledge_network:
        fail(5, "network_acknowledgement_required")
    try:
        validate_external_root(cache, repository)
        if not registry.is_file():
            raise ValueError("missing registry")
    except (OSError, ValueError):
        fail(2, "unsafe_external_storage")
    emit(
        {
            "status": "not_started",
            "network_authorized": True,
            "adapter_required": True,
            "cache": str(cache.resolve()),
        }
    )


@app.command("readiness")
def readiness(
    snapshot: Annotated[Path, typer.Option("--snapshot")],
) -> None:
    try:
        value = load_experiment_artifact(snapshot, ExternalReadiness)
    except (OSError, ValueError):
        fail(2, "invalid_external_readiness")
    emit(
        {
            "status": value.overall_status,
            "gate_count": len(value.gates),
            "readiness_fingerprint": value.readiness_fingerprint,
        }
    )


@profile_app.command("apply-review")
def apply_review(review: Annotated[Path, typer.Option("--review")]) -> None:
    try:
        value = load_experiment_artifact(review, ProfileReviewDecision)
    except (OSError, ValueError):
        fail(2, "invalid_profile_review")
    emit(
        {
            "status": "review_validated",
            "decision": value.decision,
            "profile_fingerprint": value.profile_fingerprint,
        }
    )
