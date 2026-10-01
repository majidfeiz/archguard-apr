"""Provider configuration and opt-in connectivity commands."""

import json
from pathlib import Path
from typing import Annotated, Never

import typer
from pydantic import ValidationError

from archguard.domain.providers import ProviderCapabilities
from archguard.infrastructure.providers.anthropic_messages import (
    CAPABILITIES as ANTHROPIC_CAPABILITIES,
)
from archguard.infrastructure.providers.configuration import (
    ProviderConfiguration,
    load_provider_configuration,
)
from archguard.infrastructure.providers.credentials import credential_for
from archguard.infrastructure.providers.openai_responses import CAPABILITIES as OPENAI_CAPABILITIES

app = typer.Typer(no_args_is_help=True)
config_app = typer.Typer(no_args_is_help=True)
app.add_typer(config_app, name="config")


def fail(code: int, diagnostic: str) -> Never:
    typer.echo(json.dumps({"diagnostic_code": diagnostic, "status": "error"}, sort_keys=True))
    raise typer.Exit(code)


def load(path: Path) -> ProviderConfiguration:
    try:
        return load_provider_configuration(path)
    except (OSError, ValueError, ValidationError):
        fail(2, "invalid_provider_configuration")


@config_app.command("validate")
def validate(config: Annotated[Path, typer.Option("--config")]) -> None:
    value = load(config)
    typer.echo(
        json.dumps(
            {"providers": len(value.providers), "schema": value.schema_version, "status": "valid"},
            sort_keys=True,
        )
    )


@app.command("list")
def list_providers(config: Annotated[Path, typer.Option("--config")]) -> None:
    value = load(config)
    typer.echo(
        json.dumps(
            {
                "providers": [
                    {"provider": item.provider, "model": item.model} for item in value.providers
                ]
            },
            sort_keys=True,
        )
    )


def known(provider: str) -> ProviderCapabilities:
    values = {"openai": OPENAI_CAPABILITIES, "anthropic": ANTHROPIC_CAPABILITIES}
    if provider not in values:
        fail(2, "unknown_provider")
    return values[provider]


@app.command("capabilities")
def capabilities(
    provider: Annotated[str, typer.Option("--provider")],
    config: Annotated[Path, typer.Option("--config")],
) -> None:
    value = load(config)
    if provider not in {item.provider for item in value.providers}:
        fail(2, "provider_not_configured")
    item = known(provider)
    typer.echo(
        json.dumps(
            {"capabilities": sorted(cap.value for cap in item.values), "provider": provider},
            sort_keys=True,
        )
    )


@app.command("doctor")
def doctor(
    provider: Annotated[str, typer.Option("--provider")],
    config: Annotated[Path, typer.Option("--config")],
) -> None:
    value = load(config)
    if provider not in {item.provider for item in value.providers}:
        fail(2, "provider_not_configured")
    configured = credential_for(provider).configured
    typer.echo(
        json.dumps(
            {
                "credential": "configured" if configured else "not configured",
                "network_request": False,
                "provider": provider,
            },
            sort_keys=True,
        )
    )
    if not configured:
        raise typer.Exit(1)


@app.command("smoke-test")
def smoke_test(
    provider: Annotated[str, typer.Option("--provider")],
    config: Annotated[Path, typer.Option("--config")],
    acknowledge_cost: Annotated[bool, typer.Option("--acknowledge-cost")] = False,
) -> None:
    value = load(config)
    if provider not in {item.provider for item in value.providers}:
        fail(2, "provider_not_configured")
    if not acknowledge_cost or not value.live_execution_enabled:
        fail(2, "live_execution_not_acknowledged")
    if not credential_for(provider).configured:
        fail(1, "credential_not_configured")
    fail(2, "use_opt_in_live_test_suite")
