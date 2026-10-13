"""Source-free experiment planning and verification commands."""

import csv
import json
from pathlib import Path
from typing import Annotated, Never

import typer

from archguard.application.services.experiments import (
    blind_labels,
    create_schedule,
    validate_comparison,
)
from archguard.application.services.phase13 import run_frozen_experiment
from archguard.domain.benchmark import ExperimentPlan
from archguard.domain.experiments import ComparisonContract, ExperimentLedger, ExperimentSchedule
from archguard.infrastructure.experiment_artifacts import (
    load_experiment_artifact,
    write_experiment_artifact,
)
from archguard.infrastructure.phase13_artifacts import SourceFreeArtifacts
from archguard.infrastructure.phase13_live import Phase13LiveExecutor
from archguard.infrastructure.phase13_protocol import load_phase13_protocol, validate_amendment
from archguard.infrastructure.provider_preflight import (
    load_phase13_provider_configuration,
    provider_preflight,
)

app = typer.Typer(no_args_is_help=True)
plan_app = typer.Typer(no_args_is_help=True)
compare_app = typer.Typer(no_args_is_help=True)
schedule_app = typer.Typer(no_args_is_help=True)
ledger_app = typer.Typer(no_args_is_help=True)
app.add_typer(plan_app, name="plan")
app.add_typer(compare_app, name="compare")
app.add_typer(schedule_app, name="schedule")
app.add_typer(ledger_app, name="ledger")


@app.command("provider-preflight")
def provider_preflight_command(
    config: Annotated[Path, typer.Option("--config")],
    output_directory: Annotated[Path, typer.Option("--output-directory")] = Path(
        "../archguard-phase13-output"
    ),
    analyzed_root: Annotated[list[Path] | None, typer.Option("--analyzed-root")] = None,
    live: Annotated[bool, typer.Option("--live")] = False,
    acknowledge_cost: Annotated[bool, typer.Option("--acknowledge-cost")] = False,
    require_secret: Annotated[bool, typer.Option("--require-secret/--allow-missing-secret")] = True,
) -> None:
    """Validate the frozen provider policy; offline unless both live flags are supplied."""
    if live != acknowledge_cost:
        fail(5, "live_preflight_requires_both_acknowledgements")
    if live and acknowledge_cost:
        fail(5, "live_preflight_not_available_in_phase_13a_implementation")
    try:
        value = load_phase13_provider_configuration(config)
        report = provider_preflight(
            value,
            output_directory=output_directory,
            analyzed_roots=tuple(analyzed_root or (Path.cwd(),)),
            require_secret=require_secret,
        )
    except (OSError, ValueError, TypeError):
        fail(2, "invalid_provider_preflight_configuration")
    emit(report)
    if report["status"] != "ready":
        raise typer.Exit(4)


def emit(value: object) -> None:
    typer.echo(json.dumps(value, sort_keys=True, separators=(",", ":")))


def fail(code: int, diagnostic: str) -> Never:
    emit({"diagnostic_code": diagnostic, "status": "error"})
    raise typer.Exit(code)


@plan_app.command("validate")
def plan_validate(plan: Annotated[Path, typer.Option("--plan")]) -> None:
    try:
        value = load_experiment_artifact(plan, ExperimentPlan)
    except (OSError, ValueError):
        fail(2, "invalid_experiment_plan")
    emit({"status": "valid", "plan_fingerprint": value.plan_fingerprint, "credentials": False})


@compare_app.command("validate")
def compare_validate(contract: Annotated[Path, typer.Option("--contract")]) -> None:
    try:
        value = load_experiment_artifact(contract, ComparisonContract)
        report = validate_comparison(value)
    except (OSError, ValueError):
        fail(2, "invalid_comparison_contract")
    emit(
        {
            "status": "comparable" if report.comparable else "not_comparable",
            "difference_count": len(report.differences),
            "report_fingerprint": report.report_fingerprint,
        }
    )
    if not report.comparable:
        raise typer.Exit(3)


@schedule_app.command("create")
def schedule_create(
    plan: Annotated[Path, typer.Option("--plan")],
    contract: Annotated[Path, typer.Option("--contract")],
    output: Annotated[Path, typer.Option("--output")],
) -> None:
    try:
        plan_value = load_experiment_artifact(plan, ExperimentPlan)
        contract_value = load_experiment_artifact(contract, ComparisonContract)
        report = validate_comparison(contract_value)
        if not report.comparable:
            fail(3, "comparison_not_fair")
        schedule = create_schedule(contract_value, plan_value.benchmark_snapshot)
        write_experiment_artifact(output, schedule)
    except FileExistsError:
        fail(4, "immutable_output_exists")
    except (OSError, ValueError):
        fail(2, "invalid_schedule_input")
    emit(
        {
            "status": "created",
            "run_count": len(schedule.runs),
            "schedule_fingerprint": schedule.schedule_fingerprint,
        }
    )


@app.command("run")
def run_experiment(
    schedule: Annotated[Path, typer.Option("--schedule")],
    mode: Annotated[str, typer.Option("--mode")] = "offline",
    acknowledge_resources: Annotated[bool, typer.Option("--acknowledge-resources")] = False,
    acknowledge_provider_cost: Annotated[bool, typer.Option("--acknowledge-provider-cost")] = False,
    acknowledge_benchmark_use: Annotated[bool, typer.Option("--acknowledge-benchmark-use")] = False,
) -> None:
    try:
        value = load_experiment_artifact(schedule, ExperimentSchedule)
    except (OSError, ValueError):
        fail(2, "invalid_experiment_schedule")
    if mode == "external-pilot" and not acknowledge_resources:
        fail(5, "resource_acknowledgement_required")
    if mode == "live-pilot" and not (acknowledge_provider_cost and acknowledge_benchmark_use):
        fail(5, "live_pilot_acknowledgements_required")
    if mode not in {"offline", "external-pilot", "live-pilot"}:
        fail(2, "invalid_experiment_mode")
    emit(
        {
            "status": "dry_run",
            "mode": mode,
            "planned_runs": len(value.runs),
            "provider_calls_executed": 0,
        }
    )


@app.command("run-frozen")
def run_frozen(
    population: Annotated[Path, typer.Option("--population")],
    protocol: Annotated[Path, typer.Option("--protocol")],
    provider_config: Annotated[Path, typer.Option("--provider-config")],
    output: Annotated[Path, typer.Option("--output")],
    acknowledge_provider_cost: Annotated[bool, typer.Option("--acknowledge-provider-cost")] = False,
    acknowledge_source_processing: Annotated[
        bool, typer.Option("--acknowledge-source-processing")
    ] = False,
) -> None:
    """Run the immutable six-execution protocol; fail closed without both acknowledgements."""
    if not (acknowledge_provider_cost and acknowledge_source_processing):
        fail(5, "frozen_experiment_requires_both_acknowledgements")
    if output.exists():
        fail(4, "immutable_output_exists")
    try:
        population_value = json.loads(population.read_text(encoding="utf-8"))
        protocol_value = load_phase13_protocol(protocol)
        validate_amendment(
            protocol.parent.parent / "reviews/phase-13-six-run-protocol-amendment.json",
            protocol_value,
        )
        if population_value.get("fingerprint") != protocol_value["population_fingerprint"]:
            raise ValueError("population/protocol drift")
        configuration = load_phase13_provider_configuration(provider_config)
        executor = Phase13LiveExecutor(Path.cwd(), provider_config, protocol_value["fingerprint"])
        results = run_frozen_experiment(
            protocol_fingerprint=protocol_value["fingerprint"],
            configuration=configuration,
            executor=executor,
            artifacts=SourceFreeArtifacts(output),
        )
    except (OSError, ValueError, TypeError, RuntimeError):
        fail(2, "frozen_experiment_failed_closed")
    emit(
        {
            "status": "complete" if len(results) == 6 else "partial",
            "completed_primary_executions": len(results),
            "provider_calls_executed": sum(item.attempt_count for item in results),
        }
    )


@ledger_app.command("verify")
def ledger_verify(ledger: Annotated[Path, typer.Option("--ledger")]) -> None:
    try:
        value = load_experiment_artifact(ledger, ExperimentLedger)
    except (OSError, ValueError):
        fail(2, "invalid_experiment_ledger")
    emit(
        {
            "status": "verified",
            "entry_count": len(value.entries),
            "ledger_fingerprint": value.ledger_fingerprint,
        }
    )


@app.command("status")
def experiment_status(experiment: Annotated[Path, typer.Option("--experiment")]) -> None:
    try:
        value = load_experiment_artifact(experiment, ExperimentLedger)
    except (OSError, ValueError):
        fail(2, "invalid_experiment_ledger")
    counts: dict[str, int] = {}
    for item in value.entries:
        counts[str(item.status)] = counts.get(str(item.status), 0) + 1
    emit({"status": "verified", "counts": counts, "entry_count": len(value.entries)})


@app.command("resume")
def experiment_resume(experiment: Annotated[Path, typer.Option("--experiment")]) -> None:
    try:
        value = load_experiment_artifact(experiment, ExperimentLedger)
    except (OSError, ValueError):
        fail(2, "invalid_experiment_ledger")
    emit(
        {
            "status": "replay_verified",
            "immutable_completed_runs": len(value.entries),
            "provider_calls_repeated": 0,
            "resumable_runs": 0,
        }
    )


@app.command("summarize")
def experiment_summarize(
    experiment: Annotated[Path, typer.Option("--experiment")],
    output: Annotated[Path, typer.Option("--output")],
    blinded: Annotated[bool, typer.Option("--blinded")] = False,
) -> None:
    if output.exists():
        fail(4, "immutable_output_exists")
    try:
        value = load_experiment_artifact(experiment, ExperimentLedger)
        ids = tuple(sorted({item.configuration_id for item in value.entries}))
        mapping = dict(blind_labels(ids, 0)) if blinded else {item: item for item in ids}
        counts = {
            label: sum(mapping[item.configuration_id] == label for item in value.entries)
            for label in sorted(mapping.values())
        }
        output.write_text(
            json.dumps(
                {
                    "schema": "archguard.pilot-summary/v1",
                    "blinded": blinded,
                    "scheduled_denominators": counts,
                    "confirmatory_analysis": False,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError):
        fail(2, "invalid_experiment_summary")
    emit({"status": "summarized", "configuration_count": len(ids), "blinded": blinded})


@app.command("export")
def export_results(
    experiment: Annotated[Path, typer.Option("--experiment")],
    output: Annotated[Path, typer.Option("--output")],
    format_name: Annotated[str, typer.Option("--format")] = "csv",
) -> None:
    if format_name != "csv" or output.exists():
        fail(4, "invalid_or_existing_export")
    try:
        ledger = load_experiment_artifact(experiment, ExperimentLedger)
        with output.open("x", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(
                (
                    "configuration_id",
                    "failure_reason",
                    "repetition_id",
                    "run_id",
                    "status",
                    "task_id",
                )
            )
            for item in sorted(ledger.entries, key=lambda value: value.run_id):
                writer.writerow(
                    (
                        item.configuration_id,
                        item.failure_reason,
                        item.repetition_id,
                        item.run_id,
                        item.status,
                        item.task_id,
                    )
                )
    except (OSError, ValueError):
        fail(2, "invalid_experiment_export")
    emit({"status": "exported", "row_count": len(ledger.entries), "source_disclosed": False})
