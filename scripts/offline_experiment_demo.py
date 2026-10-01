"""Deterministic Phase 12 experiment fixture; no source, provider, or benchmark access."""

import argparse
import csv
import json
from dataclasses import asdict
from pathlib import Path

from archguard.application.services.experiments import (
    blind_labels,
    create_schedule,
    standard_configurations,
    summarize,
    validate_comparison,
)
from archguard.domain.experiments import (
    CONTRACT_SCHEMA,
    LEDGER_SCHEMA,
    METRICS_SCHEMA,
    ComparisonContract,
    CompletionState,
    ExperimentLedger,
    ExperimentRun,
    FailureReason,
    LedgerEntry,
    RunMetrics,
)
from archguard.domain.orchestration import ArtifactReference, fingerprint


def ref(kind: str, value: str) -> ArtifactReference:
    return ArtifactReference(kind, value * 64)


def contract() -> ComparisonContract:
    tasks = tuple(f"fixture-{index}" for index in range(1, 5))
    return ComparisonContract(
        CONTRACT_SCHEMA,
        "phase12-offline",
        ref("benchmark_snapshot", "1"),
        ref("split_manifest", "2"),
        tasks,
        standard_configurations(),
        ref("profile_set", "3"),
        2,
        12012,
        (tasks[2], tasks[0], tasks[3], tasks[1]),
        "no-silent-retry/v1",
        "intention-to-run-and-valid-run/v1",
        "dated-price-table-required/v1",
        ref("metric_definitions", "4"),
        "fixture-cpu",
        ref("evaluation_tests", "5"),
    )


def metric(run_id: str, index: int) -> RunMetrics:
    resolved = index % 3 == 0
    return RunMetrics(
        METRICS_SCHEMA,
        run_id,
        resolved,
        1 if resolved else 0,
        1 if index % 7 == 0 else 0,
        index % 5 != 0,
        -1 if index % 4 == 0 else 0,
        True,
        index % 6 != 0,
        1 + index % 3,
        1 + index % 2,
        1 if index % 17 == 0 else 0,
        index % 2,
        1 if index % 19 == 0 else 0,
        1 + index % 3,
        100 + index,
        30 + index,
        0,
        None,
        None,
        500 + index * 10,
        1 + index % 2,
        512 + index,
        1 + index % 4,
        index % 3,
        0,
        0,
    )


def build() -> tuple[
    ComparisonContract, object, ExperimentLedger, object, tuple[tuple[str, str], ...]
]:
    comparison = contract()
    report = validate_comparison(comparison)
    if not report.comparable:
        raise RuntimeError("fixture comparison is not fair")
    plan = ref("experiment_plan", "6")
    schedule = create_schedule(comparison, plan)
    snapshot = comparison.benchmark_snapshot
    contract_ref = ArtifactReference("comparison_contract", comparison.contract_fingerprint)
    records = []
    entries = []
    by_config = {item.configuration_id: item for item in comparison.configurations}
    for index, scheduled in enumerate(schedule.runs):
        config = by_config[scheduled.configuration_id]
        identity = fingerprint(
            {
                "plan": plan.sha256,
                "contract": contract_ref.sha256,
                "configuration": config.configuration_id,
                "task": scheduled.task_id,
                "repetition": scheduled.repetition_id,
                "provider_model": f"{config.provider}/{config.model}",
                "prompt": config.prompt_version,
                "snapshot": snapshot.sha256,
            }
        )
        if index % 11 == 0:
            state, reason, metrics = (
                CompletionState.INFRASTRUCTURE_FAILURE,
                FailureReason.SANDBOX_TIMEOUT,
                None,
            )
        elif index % 13 == 0:
            state, reason, metrics = CompletionState.MISSING, FailureReason.PROVIDER_REFUSAL, None
        else:
            metrics = metric(identity, index)
            state = (
                CompletionState.COMPLETED if metrics.task_resolved else CompletionState.UNRESOLVED
            )
            reason = FailureReason.NONE
        metrics_ref = (
            ArtifactReference("run_metrics", metrics.metrics_fingerprint) if metrics else None
        )
        run = ExperimentRun(
            "archguard.experiment-run/v1",
            plan,
            contract_ref,
            snapshot,
            config.configuration_id,
            scheduled.task_id,
            scheduled.repetition_id,
            scheduled.run_seed,
            f"{config.provider}/{config.model}",
            config.prompt_version,
            state,
            (),
            None,
            None,
            ref("evaluation_evidence", "7") if metrics else None,
            metrics_ref,
            reason,
            ref("resource_telemetry", "8"),
        )
        records.append((config.configuration_id, run, metrics))
        entries.append(
            LedgerEntry(
                run.run_id,
                config.configuration_id,
                run.task_id,
                run.repetition_id,
                state,
                ArtifactReference("experiment_run", fingerprint(asdict(run))),
                reason,
            )
        )
    mapping = blind_labels(tuple(by_config), comparison.seed)
    summary = summarize(tuple(records), dict(mapping))
    ledger = ExperimentLedger(
        LEDGER_SCHEMA,
        "phase12-offline",
        "6" * 64,
        comparison.contract_fingerprint,
        "9" * 64,
        tuple(entries),
    )
    return comparison, schedule, ledger, summary, mapping


def write(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    comparison, schedule, ledger, summary, mapping = build()
    artifacts = {
        "comparison.json": asdict(comparison),
        "schedule.json": asdict(schedule),
        "ledger.json": asdict(ledger),
        "summary.json": asdict(summary),
        "blind-mapping.json": {"mapping": mapping, "controlled": True},
    }
    for name, value in artifacts.items():
        (output / name).write_text(
            json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
        )
    with (output / "results.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(
            ("configuration_id", "failure_reason", "repetition_id", "run_id", "status", "task_id")
        )
        for item in sorted(ledger.entries, key=lambda entry: entry.run_id):
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write(args.output)


if __name__ == "__main__":
    main()
