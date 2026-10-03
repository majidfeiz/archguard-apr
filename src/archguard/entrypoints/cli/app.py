import json
import shutil
import sys
from pathlib import Path
from typing import Annotated, Never

import typer
from pydantic import ValidationError

from archguard import __version__
from archguard.entrypoints.cli.architecture import app as architecture_app
from archguard.entrypoints.cli.benchmark import app as benchmark_app
from archguard.entrypoints.cli.context import app as context_app
from archguard.entrypoints.cli.execution import app as execution_app
from archguard.entrypoints.cli.experiment import app as experiment_runner_app
from archguard.entrypoints.cli.graph import app as graph_app
from archguard.entrypoints.cli.patch import app as patch_app
from archguard.entrypoints.cli.provider import app as provider_app
from archguard.entrypoints.cli.readiness import app as readiness_app
from archguard.entrypoints.cli.repair import app as repair_app
from archguard.entrypoints.cli.repository import app as repository_app
from archguard.infrastructure.config import Settings, load_settings, read_yaml
from archguard.infrastructure.logging import redact
from archguard.infrastructure.paths import writable_directory
from archguard.schemas.experiment import ExperimentMetadata

app = typer.Typer(no_args_is_help=True)
app.add_typer(repository_app, name="repository")
app.add_typer(benchmark_app, name="benchmark")
app.add_typer(graph_app, name="graph")
app.add_typer(architecture_app, name="architecture")
app.add_typer(patch_app, name="patch")
app.add_typer(context_app, name="context")
app.add_typer(execution_app, name="execution")
app.add_typer(repair_app, name="repair")
app.add_typer(provider_app, name="provider")
app.add_typer(readiness_app, name="readiness")
config_app = typer.Typer()
experiment_app = experiment_runner_app
app.add_typer(config_app, name="config")
app.add_typer(experiment_app, name="experiment")


def fail(error: Exception) -> Never:
    if isinstance(error, ValidationError):
        message = "; ".join(
            ".".join(map(str, e["loc"])) + ": " + e["type"]
            for e in error.errors(include_input=False)
        )
    else:
        message = redact(str(error))
    typer.echo("Error: " + message, err=True)
    raise typer.Exit(2)


def settings_or_exit(path: Path | None) -> Settings:
    try:
        return load_settings(path)
    except (ValueError, OSError) as error:
        fail(error)


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)


@config_app.command("show")
def config_show(config: Annotated[Path | None, typer.Option("--config")] = None) -> None:
    """Show effective configuration; environment overrides YAML."""
    settings = settings_or_exit(config)
    typer.echo(redact(json.dumps(settings.model_dump(mode="json"), sort_keys=True, indent=2)))


@app.command()
def doctor(config: Annotated[Path | None, typer.Option("--config")] = None) -> None:
    """Probe local prerequisites without contacting the Docker daemon."""
    settings = settings_or_exit(config)
    checks = {
        "python_supported": (3, 12) <= sys.version_info[:2] < (3, 14),
        "configuration_valid": True,
        "workspace_available": settings.workspace_dir.is_dir(),
        "output_writable": writable_directory(settings.experiment_output_dir),
        "git_available": shutil.which("git") is not None,
        "docker_executable_available": shutil.which("docker") is not None,
    }
    typer.echo(
        json.dumps({**checks, "docker_daemon": "not checked (not required)"}, sort_keys=True)
    )
    if not all(value for key, value in checks.items() if key != "docker_executable_available"):
        raise typer.Exit(1)


@experiment_app.command("validate")
def experiment_validate(config: Annotated[Path, typer.Option("--config")]) -> None:
    """Validate metadata only, with no repository or provider execution."""
    try:
        metadata = ExperimentMetadata.model_validate(read_yaml(config))
    except (ValueError, OSError) as error:
        fail(error)
    typer.echo(metadata.canonical_json())
