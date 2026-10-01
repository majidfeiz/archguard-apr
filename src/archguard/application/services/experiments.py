"""Deterministic comparison, scheduling, lexical retrieval, blinding, and summaries."""

import hashlib
import re
from collections.abc import Mapping
from dataclasses import fields, replace

from archguard.domain.experiments import (
    CONFIG_SCHEMA,
    FAIRNESS_SCHEMA,
    SCHEDULE_SCHEMA,
    SUMMARY_SCHEMA,
    ComparisonContract,
    CompletionState,
    DescriptiveStatistics,
    ExperimentRun,
    ExperimentSchedule,
    FairnessDifference,
    FairnessReport,
    PilotSummary,
    RunMetrics,
    ScheduledRun,
    SystemConfiguration,
)
from archguard.domain.orchestration import ArtifactReference, fingerprint
from archguard.domain.repository import check

COMPONENTS = (
    "graph_retrieval",
    "architecture_awareness",
    "multi_agent",
    "execution_feedback",
    "iterative_refinement",
    "evidence_ranking",
)
FAIR_FIELDS = (
    "provider",
    "model",
    "model_revision",
    "prompt_version",
    "context_budget",
    "output_budget",
    "candidate_budget",
    "round_budget",
    "timeout_seconds",
    "sandbox_image",
    "retry_policy",
)
ABLATION_FACTORS = {
    "C2": "architecture_awareness",
    "C3": "graph_retrieval",
    "C4": "execution_feedback",
    "C5": "multi_agent",
    "C6": "iterative_refinement",
}


def standard_configurations() -> tuple[SystemConfiguration, ...]:
    full = SystemConfiguration(
        CONFIG_SCHEMA,
        "C1",
        "frozen-provider",
        "frozen-model",
        "recorded-at-run",
        "phase12-v1",
        16_384,
        4_096,
        3,
        3,
        900,
        "sha256:" + "1" * 64,
        "no-silent-retry/v1",
        True,
        True,
        True,
        True,
        True,
        True,
    )
    configs = [
        replace(
            full,
            configuration_id="C0",
            candidate_budget=1,
            round_budget=1,
            graph_retrieval=False,
            architecture_awareness=False,
            multi_agent=False,
            execution_feedback=False,
            iterative_refinement=False,
            evidence_ranking=False,
            configuration_fingerprint="",
        ),
        full,
    ]
    configs.extend(
        (
            replace(
                full,
                configuration_id="C2",
                architecture_awareness=False,
                configuration_fingerprint="",
            ),
            replace(
                full, configuration_id="C3", graph_retrieval=False, configuration_fingerprint=""
            ),
            replace(
                full, configuration_id="C4", execution_feedback=False, configuration_fingerprint=""
            ),
            replace(full, configuration_id="C5", multi_agent=False, configuration_fingerprint=""),
            replace(
                full,
                configuration_id="C6",
                iterative_refinement=False,
                configuration_fingerprint="",
            ),
        )
    )
    return tuple(sorted(configs, key=lambda item: item.configuration_id))


def validate_comparison(contract: ComparisonContract) -> FairnessReport:
    by_id = {item.configuration_id: item for item in contract.configurations}
    check("C1" in by_id, "comparison requires C1")
    full = by_id["C1"]
    differences: list[FairnessDifference] = []
    for identifier, config in sorted(by_id.items()):
        if identifier == "C1":
            continue
        permitted_factor = ABLATION_FACTORS.get(identifier)
        for field in FAIR_FIELDS + COMPONENTS:
            expected = getattr(full, field)
            actual = getattr(config, field)
            if expected != actual:
                permitted = identifier == "C0" or field == permitted_factor
                differences.append(
                    FairnessDifference(identifier, field, str(expected), str(actual), permitted)
                )
        if (
            permitted_factor
            and sum(item.configuration_id == identifier and item.permitted for item in differences)
            != 1
        ):
            differences.append(
                FairnessDifference(identifier, "conceptual_factor_count", "1", "not-1", False)
            )
    ordered = tuple(sorted(differences, key=lambda item: (item.configuration_id, item.field)))
    return FairnessReport(FAIRNESS_SCHEMA, all(item.permitted for item in ordered), ordered)


def create_schedule(
    contract: ComparisonContract, experiment_plan: ArtifactReference
) -> ExperimentSchedule:
    runs: list[ScheduledRun] = []
    index = 0
    for task_id in contract.task_order:
        for repetition in range(1, contract.repetition_count + 1):
            configurations = sorted(
                contract.configurations,
                key=lambda item: hashlib.sha256(
                    f"{contract.seed}:{task_id}:{repetition}:{item.configuration_id}".encode()
                ).hexdigest(),
            )
            for config in configurations:
                run_seed = int(
                    hashlib.sha256(
                        f"{contract.seed}:{task_id}:{repetition}:{config.configuration_id}".encode()
                    ).hexdigest()[:16],
                    16,
                )
                run_id = fingerprint(
                    {
                        "plan": experiment_plan.sha256,
                        "contract": contract.contract_fingerprint,
                        "configuration": config.configuration_fingerprint,
                        "task": task_id,
                        "repetition": repetition,
                    }
                )
                runs.append(
                    ScheduledRun(
                        index, config.configuration_id, task_id, repetition, run_seed, run_id
                    )
                )
                index += 1
    return ExperimentSchedule(
        SCHEDULE_SCHEMA,
        experiment_plan,
        ArtifactReference("comparison_contract", contract.contract_fingerprint),
        tuple(runs),
    )


def lexical_context(
    issue: str, documents: Mapping[str, str], maximum_bytes: int
) -> tuple[tuple[str, int], ...]:
    """Rank paths by integer term frequency; no graph, oracle, or fixed-revision input."""
    check(maximum_bytes > 0, "context budget must be positive")
    terms = tuple(sorted(set(re.findall(r"[A-Za-z_][A-Za-z0-9_]+", issue.lower()))))
    scored = []
    for path, text in documents.items():
        lowered = f"{path}\n{text}".lower()
        score = sum(lowered.count(term) for term in terms)
        scored.append((path, score, len(text.encode())))
    selected: list[tuple[str, int]] = []
    consumed = 0
    for path, score, size in sorted(scored, key=lambda item: (-item[1], item[0])):
        if consumed + size <= maximum_bytes:
            selected.append((path, score))
            consumed += size
    return tuple(selected)


def blind_labels(configuration_ids: tuple[str, ...], seed: int) -> tuple[tuple[str, str], ...]:
    ordered = sorted(
        set(configuration_ids),
        key=lambda item: hashlib.sha256(f"blind:{seed}:{item}".encode()).hexdigest(),
    )
    return tuple(
        sorted(
            (identifier, f"SYSTEM_{chr(65 + index)}") for index, identifier in enumerate(ordered)
        )
    )


def summarize(
    records: tuple[tuple[str, ExperimentRun, RunMetrics | None], ...],
    labels: Mapping[str, str],
) -> PilotSummary:
    by_label: dict[str, list[tuple[ExperimentRun, RunMetrics | None]]] = {}
    for configuration, run, metrics in records:
        by_label.setdefault(labels.get(configuration, configuration), []).append((run, metrics))
    intention: list[tuple[str, int, int, int]] = []
    sensitivity: list[tuple[str, int, int]] = []
    missing = infrastructure = 0
    for label, values in sorted(by_label.items()):
        resolved = sum(
            metrics is not None and metrics.task_resolved is True for _, metrics in values
        )
        valid = [(run, metrics) for run, metrics in values if metrics is not None]
        intention.append((label, resolved, len(values), len(valid)))
        sensitivity.append((label, resolved, len(valid)))
        missing += sum(run.completion_state == CompletionState.MISSING for run, _ in values)
        infrastructure += sum(
            run.completion_state == CompletionState.INFRASTRUCTURE_FAILURE for run, _ in values
        )
    label_values = tuple(sorted(by_label))
    return PilotSummary(
        SUMMARY_SCHEMA, label_values, tuple(intention), tuple(sensitivity), missing, infrastructure
    )


def public_metric_fields() -> tuple[str, ...]:
    return tuple(field.name for field in fields(RunMetrics) if field.name != "metrics_fingerprint")


def descriptive_statistics(values: tuple[int | None, ...]) -> DescriptiveStatistics:
    observed = sorted(value for value in values if value is not None)
    if not observed:
        return DescriptiveStatistics(0, len(values), None, None, None, None, None)

    def percentile(numerator: int) -> int:
        index = ((len(observed) - 1) * numerator + 2) // 4
        return observed[index]

    return DescriptiveStatistics(
        len(observed),
        len(values) - len(observed),
        observed[0],
        percentile(1),
        percentile(2),
        percentile(3),
        observed[-1],
    )


def paired_differences(
    left: Mapping[tuple[str, int], int | None],
    right: Mapping[tuple[str, int], int | None],
) -> tuple[tuple[str, int, int], ...]:
    common = sorted(set(left) & set(right))
    differences = []
    for task, repetition in common:
        left_value = left[(task, repetition)]
        right_value = right[(task, repetition)]
        if left_value is not None and right_value is not None:
            differences.append((task, repetition, right_value - left_value))
    return tuple(differences)
