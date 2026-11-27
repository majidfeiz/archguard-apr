"""Explicit commands for offline validation, fake dry-runs and authorized V2.2 execution."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import typer

from archguard.application.ports.v2_execution import ProviderAdmissionFailure
from archguard.application.services.v2_execution import V2MicroPilotRunner
from archguard.domain.canonical import canonical_json
from archguard.domain.v2_execution import BudgetLedger
from archguard.infrastructure.artifact_io import atomic_write
from archguard.infrastructure.v2_evidence import (
    AtomicCheckpointStore,
    import_evidence,
    load_checkpoint,
    validate_source_free,
    write_run_evidence,
)
from archguard.infrastructure.v2_protocol import FrozenProtocol, load_frozen_protocol
from archguard.infrastructure.v2_runtime import (
    DeterministicFakeProvider,
    FakePreparer,
    FakeProcessor,
    NoopCleanup,
    V2CapabilityProbe,
    V2OpenAIProvider,
    V2Workspace,
)

app = typer.Typer(no_args_is_help=True)
AUTHORIZATION = "AUTHORIZE_V2_MICRO_PILOT_8_CALLS_USD_1"
CAPABILITY_PROBE_AUTHORIZATION = "AUTHORIZE_V2_PROVIDER_CAPABILITY_PROBE_REASONING_FIX_1_CALL"


def _protocol(root: Path) -> FrozenProtocol:
    return load_frozen_protocol(root)


@app.command("protocol-validate")
def protocol_validate(root: Annotated[Path, typer.Option("--root")] = Path(".")) -> None:
    """Validate every frozen protocol binding without source or provider access."""
    protocol = _protocol(root)
    typer.echo(json.dumps({"status": "VALID", "fingerprint": protocol.fingerprint}, sort_keys=True))


@app.command("dry-run")
def dry_run(
    output: Annotated[Path, typer.Option("--output")],
    root: Annotated[Path, typer.Option("--root")] = Path("."),
) -> None:
    """Run all eight ordinals using deterministic source-free fakes."""
    protocol = _protocol(root)
    output.mkdir(parents=True, exist_ok=False)
    checkpoint = AtomicCheckpointStore(output / "checkpoint.json")
    provider = DeterministicFakeProvider()
    runner = V2MicroPilotRunner(
        FakePreparer(protocol.fairness_fingerprint),
        provider,
        FakeProcessor(),
        checkpoint,
        NoopCleanup(),
    )
    ledger, results, failures, cleaned = runner.run()
    archive = write_run_evidence(
        output,
        ledger,
        results,
        failures,
        protocol_fingerprint=protocol.fingerprint,
        fairness_fingerprint=protocol.fairness_fingerprint,
        cleanup_complete=cleaned,
    )
    typer.echo(json.dumps({"calls": len(provider.calls), "evidence": str(archive)}, sort_keys=True))


@app.command("execute")
def execute(
    output: Annotated[Path, typer.Option("--output")],
    authorization: Annotated[str, typer.Option("--authorization")],
    root: Annotated[Path, typer.Option("--root")] = Path("."),
) -> None:
    """Execute or resume the real, sequential run after exact human authorization."""
    if authorization != AUTHORIZATION:
        raise typer.BadParameter("exact V2 micro-pilot authorization is required")
    protocol = _protocol(root)
    resolved_output = output.resolve()
    try:
        resolved_output.relative_to(protocol.root)
    except ValueError:
        pass
    else:
        raise typer.BadParameter("execution output must remain outside the analyzed repository")
    resolved_output.mkdir(parents=True, exist_ok=True)
    checkpoint_path = resolved_output / "checkpoint.json"
    ledger, carried, failures = (
        load_checkpoint(checkpoint_path) if checkpoint_path.exists() else (BudgetLedger(), (), ())
    )
    carried_attempts = ledger.provider_request_attempts
    if ledger.failed_attempt_ordinals:
        raise typer.BadParameter(
            "failed scientific ordinal cannot be repeated without a prospective protocol amendment"
        )
    workspace = V2Workspace(protocol)
    runner = V2MicroPilotRunner(
        workspace,
        V2OpenAIProvider(),
        workspace,
        AtomicCheckpointStore(checkpoint_path, carried_attempts),
        workspace,
    )
    try:
        ledger, results, failures, cleaned = runner.run(ledger, carried, failures)
    finally:
        if checkpoint_path.exists():
            ledger, results, failures = load_checkpoint(checkpoint_path)
            write_run_evidence(
                resolved_output,
                ledger,
                results,
                failures,
                protocol_fingerprint=protocol.fingerprint,
                fairness_fingerprint=protocol.fairness_fingerprint,
                cleanup_complete=not workspace.root.exists(),
                carried_calls=carried_attempts,
            )
    typer.echo(
        json.dumps({"completed_calls": ledger.completed_calls, "cleanup": cleaned}, sort_keys=True)
    )


@app.command("checkpoint-validate")
def checkpoint_validate(path: Annotated[Path, typer.Argument()]) -> None:
    ledger, results, failures = load_checkpoint(path)
    typer.echo(
        json.dumps(
            {
                "provider_request_attempts": ledger.provider_request_attempts,
                "accepted_provider_calls": ledger.accepted_provider_calls,
                "completed_scientific_executions": ledger.completed_calls,
                "infrastructure_failures": ledger.infrastructure_failures,
                "results": len(results),
                "failure_records": len(failures),
            },
            sort_keys=True,
        )
    )


@app.command("evidence-validate")
def evidence_validate(path: Annotated[Path, typer.Argument()]) -> None:
    import tempfile

    with tempfile.TemporaryDirectory(prefix="archguard-v2-evidence-") as temporary:
        import_evidence(path, Path(temporary))
    typer.echo("VALID")


@app.command("evidence-import")
def evidence_import(
    path: Annotated[Path, typer.Argument()],
    destination: Annotated[Path, typer.Option("--destination")],
) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    import_evidence(path, destination)
    typer.echo("IMPORTED")


@app.command("aggregate")
def aggregate(
    checkpoint: Annotated[Path, typer.Argument()], output: Annotated[Path, typer.Option("--output")]
) -> None:
    ledger, results, failures = load_checkpoint(checkpoint)
    value = {
        "schema": "archguard.v2-micro-pilot-aggregate/v1",
        "completed": ledger.completed_calls,
        "provider_request_attempts": ledger.provider_request_attempts,
        "accepted_provider_calls": ledger.accepted_provider_calls,
        "infrastructure_failures": ledger.infrastructure_failures,
        "remaining": ledger.remaining_calls,
        "classifications": [item.terminal_classification.value for item in results],
        "provider_failure_kinds": [item.diagnostic.kind.value for item in failures],
    }
    validate_source_free(value)
    atomic_write(output, canonical_json(value))
    typer.echo(str(output))


@app.command("capability-probe")
def capability_probe(
    output: Annotated[Path, typer.Option("--output")],
    authorization: Annotated[str, typer.Option("--authorization")],
) -> None:
    """Run one separately authorized operational provider capability probe."""
    if authorization != CAPABILITY_PROBE_AUTHORIZATION:
        raise typer.BadParameter("exact provider capability-probe authorization is required")
    try:
        result = V2CapabilityProbe().run().as_source_free_dict()
    except ValueError:
        result = {
            "schema": "archguard.v2-provider-capability-probe/v1",
            "status": "PRE_PROVIDER_BLOCKED",
            "provider_request_attempts": 0,
            "accepted_provider_calls": 0,
            "scientific_executions": 0,
        }
        validate_source_free(result)
        atomic_write(output, canonical_json(result))
        typer.echo(json.dumps(result, sort_keys=True))
        raise typer.Exit(3) from None
    except ProviderAdmissionFailure as error:
        result = {
            "schema": "archguard.v2-provider-capability-probe/v1",
            "status": "PROVIDER_REJECTED",
            "provider_request_attempts": 1,
            "accepted_provider_calls": 0,
            "scientific_executions": 0,
            "diagnostic": asdict(error.diagnostic),
        }
        validate_source_free(result)
        atomic_write(output, canonical_json(result))
        typer.echo(json.dumps(result, sort_keys=True))
        raise typer.Exit(3) from None
    validate_source_free(result)
    atomic_write(output, canonical_json(result))
    typer.echo(json.dumps(result, sort_keys=True))
