"""Offline benchmark registry and cache commands."""

import json
from pathlib import Path
from typing import Annotated, Never

import typer

from archguard.infrastructure.benchmark import load_registry, load_snapshot, verify_cache

app = typer.Typer(no_args_is_help=True)
registry_app = typer.Typer(no_args_is_help=True)
cache_app = typer.Typer(no_args_is_help=True)
tasks_app = typer.Typer(no_args_is_help=True)
task_app = typer.Typer(no_args_is_help=True)
app.add_typer(registry_app, name="registry")
app.add_typer(cache_app, name="cache")
app.add_typer(tasks_app, name="tasks")
app.add_typer(task_app, name="task")


def emit(value: object) -> None:
    typer.echo(json.dumps(value, sort_keys=True, separators=(",", ":")))


def fail(code: int, diagnostic: str) -> Never:
    emit({"diagnostic_code": diagnostic, "status": "error"})
    raise typer.Exit(code)


@registry_app.command("validate")
def validate_registry(registry: Annotated[Path, typer.Option("--registry")]) -> None:
    try:
        value = load_registry(registry)
    except (OSError, ValueError):
        fail(2, "invalid_benchmark_registry")
    emit(
        {
            "status": "valid",
            "benchmark_count": len(value.entries),
            "registry_fingerprint": value.registry_fingerprint,
            "network_access": False,
        }
    )


@registry_app.command("inspect")
def inspect_registry(registry: Annotated[Path, typer.Option("--registry")]) -> None:
    try:
        value = load_registry(registry)
    except (OSError, ValueError):
        fail(2, "invalid_benchmark_registry")
    emit(
        {
            "benchmarks": [
                {
                    "benchmark_id": item.benchmark_id,
                    "kind": item.kind,
                    "license_identifier": item.license_identifier,
                    "redistribution_status": item.redistribution_status,
                }
                for item in value.entries
            ],
            "registry_fingerprint": value.registry_fingerprint,
        }
    )


@cache_app.command("verify")
def cache_verify(cache: Annotated[Path, typer.Option("--cache")]) -> None:
    try:
        emit(verify_cache(cache))
    except (OSError, ValueError):
        fail(3, "invalid_benchmark_cache")


@cache_app.command("inspect")
def cache_inspect(cache: Annotated[Path, typer.Option("--cache")]) -> None:
    cache_verify(cache)


@tasks_app.command("list")
def tasks_list(snapshot: Annotated[Path, typer.Option("--snapshot")]) -> None:
    try:
        value = load_snapshot(snapshot)
    except (OSError, ValueError):
        fail(2, "invalid_benchmark_snapshot")
    emit(
        {
            "tasks": [
                {
                    "task_id": task.task_id,
                    "benchmark_id": task.benchmark_id,
                    "state": task.state,
                    "split": task.split,
                }
                for task in value.tasks
            ]
        }
    )


@task_app.command("inspect")
def task_inspect(
    snapshot: Annotated[Path, typer.Option("--snapshot")],
    task_id: Annotated[str, typer.Option("--task")],
) -> None:
    try:
        value = load_snapshot(snapshot)
        selected = next(item for item in value.tasks if item.task_id == task_id)
    except (OSError, ValueError, StopIteration):
        fail(2, "benchmark_task_not_found")
    emit(
        {
            "task_id": selected.task_id,
            "benchmark_id": selected.benchmark_id,
            "project_id": selected.project_id,
            "state": selected.state,
            "split": selected.split,
            "sensitivity": selected.sensitivity,
            "exclusion_reasons": selected.exclusion_reasons,
            "task_fingerprint": selected.task_fingerprint,
        }
    )


@app.command("acquire")
def acquire(
    registry: Annotated[Path, typer.Option("--registry")],
    cache: Annotated[Path, typer.Option("--cache")],
) -> None:
    load_registry(registry)
    if cache.exists():
        fail(2, "cache_destination_exists")
    emit(
        {
            "status": "not_started",
            "network_required": True,
            "diagnostic_code": "explicit_acquisition_adapter_required",
        }
    )
    raise typer.Exit(4)
