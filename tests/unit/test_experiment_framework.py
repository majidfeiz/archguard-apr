from dataclasses import asdict, replace

import pytest

from archguard.application.services.experiments import (
    blind_labels,
    create_schedule,
    descriptive_statistics,
    lexical_context,
    paired_differences,
    standard_configurations,
    summarize,
    validate_comparison,
)
from archguard.domain.benchmark import DatasetSplit
from archguard.domain.experiments import (
    CONTRACT_SCHEMA,
    METRICS_SCHEMA,
    ComparisonContract,
    CompletionState,
    ExperimentRun,
    FailureReason,
    RunMetrics,
    require_pilot_split,
)
from archguard.domain.orchestration import ArtifactReference


def ref(kind: str, char: str) -> ArtifactReference:
    return ArtifactReference(kind, char * 64)


def contract() -> ComparisonContract:
    return ComparisonContract(
        CONTRACT_SCHEMA,
        "test-comparison",
        ref("snapshot", "1"),
        ref("splits", "2"),
        ("task-a", "task-b"),
        standard_configurations(),
        ref("profiles", "3"),
        3,
        42,
        ("task-b", "task-a"),
        "no-retry",
        "intent-and-valid",
        "dated-price-table",
        ref("metrics", "4"),
        "linux-x86_64",
        ref("tests", "5"),
    )


def metrics(run_id: str, resolved: bool = True) -> RunMetrics:
    return RunMetrics(
        METRICS_SCHEMA,
        run_id,
        resolved,
        int(resolved),
        0,
        True,
        0,
        True,
        True,
        2,
        1,
        0,
        0,
        0,
        1,
        100,
        20,
        0,
        None,
        None,
        500,
        1,
        1000,
        2,
        1,
        0,
        0,
    )


def run(
    configuration: str, state: CompletionState, with_metrics: bool = True
) -> tuple[ExperimentRun, RunMetrics | None]:
    plan, comparison, snapshot = ref("plan", "6"), ref("contract", "7"), ref("snapshot", "1")
    expected = ExperimentRun(
        "archguard.experiment-run/v1",
        plan,
        comparison,
        snapshot,
        configuration,
        "task-a",
        1,
        9,
        "provider/model",
        "v1",
        state,
        (),
        None,
        None,
        ref("evidence", "8") if with_metrics else None,
        ref("metrics", "9") if with_metrics else None,
        FailureReason.NONE if with_metrics else FailureReason.SANDBOX_TIMEOUT,
        ref("telemetry", "a"),
    )
    return expected, metrics(expected.run_id) if with_metrics else None


def test_standard_configurations_are_one_factor_ablations() -> None:
    configurations = standard_configurations()
    assert tuple(item.configuration_id for item in configurations) == (
        "C0",
        "C1",
        "C2",
        "C3",
        "C4",
        "C5",
        "C6",
    )
    report = validate_comparison(contract())
    assert report.comparable
    assert all(item.permitted for item in report.differences)


def test_fairness_reports_all_unrelated_differences() -> None:
    value = contract()
    changed = tuple(
        replace(item, model="unfair", configuration_fingerprint="")
        if item.configuration_id == "C2"
        else item
        for item in value.configurations
    )
    report = validate_comparison(replace(value, configurations=changed, contract_fingerprint=""))
    assert not report.comparable
    assert any(
        item.configuration_id == "C2" and item.field == "model" and not item.permitted
        for item in report.differences
    )


def test_schedule_is_deterministic_blocked_and_idempotent() -> None:
    value = contract()
    one = create_schedule(value, ref("plan", "6"))
    two = create_schedule(value, ref("plan", "6"))
    assert one == two
    assert len(one.runs) == 2 * 3 * 7
    assert len({item.run_id for item in one.runs}) == len(one.runs)
    assert {item.configuration_id for item in one.runs[:7]} == {f"C{x}" for x in range(7)}
    changed = create_schedule(replace(value, seed=43, contract_fingerprint=""), ref("plan", "6"))
    assert changed.schedule_fingerprint != one.schedule_fingerprint


def test_evaluation_split_is_never_accessible() -> None:
    require_pilot_split(DatasetSplit.DEVELOPMENT)
    require_pilot_split(DatasetSplit.PILOT)
    for split in (DatasetSplit.EVALUATION, DatasetSplit.EXCLUDED):
        with pytest.raises(ValueError, match="inaccessible"):
            require_pilot_split(split)


def test_non_graph_context_is_stable_budgeted_lexical_only() -> None:
    documents = {"z.py": "needle", "a.py": "needle needle", "large.py": "x" * 100}
    assert lexical_context("needle", documents, 20) == (("a.py", 2), ("z.py", 1))
    assert lexical_context("needle", dict(reversed(tuple(documents.items()))), 20) == (
        ("a.py", 2),
        ("z.py", 1),
    )


def test_blinding_is_seeded_and_separate() -> None:
    one = blind_labels(("C2", "C0", "C1"), 4)
    assert one == blind_labels(("C1", "C2", "C0"), 4)
    assert {label for _, label in one} == {"SYSTEM_A", "SYSTEM_B", "SYSTEM_C"}
    assert one != blind_labels(("C2", "C0", "C1"), 5)


def test_summary_separates_intention_valid_missing_and_infrastructure() -> None:
    completed, completed_metrics = run("C0", CompletionState.COMPLETED)
    infrastructure, no_metrics = run("C0", CompletionState.INFRASTRUCTURE_FAILURE, False)
    missing = replace(
        infrastructure,
        completion_state=CompletionState.MISSING,
        failure_reason=FailureReason.PROVIDER_REFUSAL,
        run_id="",
    )
    summary = summarize(
        (
            ("C0", completed, completed_metrics),
            ("C0", infrastructure, no_metrics),
            ("C0", missing, None),
        ),
        {"C0": "SYSTEM_A"},
    )
    assert summary.intention_to_run == (("SYSTEM_A", 1, 3, 1),)
    assert summary.valid_run_sensitivity == (("SYSTEM_A", 1, 1),)
    assert summary.infrastructure_failure_count == summary.missing_count == 1


def test_run_identity_changes_with_repetition_and_completed_is_immutable() -> None:
    value, _ = run("C1", CompletionState.COMPLETED)
    changed = replace(value, repetition_id=2, run_id="")
    assert changed.run_id != value.run_id
    with pytest.raises(ValueError, match="identity"):
        replace(value, run_id="0" * 64)


def test_metric_record_is_source_free_and_fingerprinted() -> None:
    value = metrics("a" * 64)
    assert len(value.metrics_fingerprint) == 64
    assert not ({"source", "patch", "prompt", "hidden_tests"} & set(asdict(value)))
    with pytest.raises(ValueError, match="fingerprint"):
        replace(value, metrics_fingerprint="0" * 64)


def test_descriptive_statistics_and_paired_differences_preserve_missingness() -> None:
    distribution = descriptive_statistics((1, 2, 3, 4, None))
    assert (distribution.count, distribution.missing, distribution.median) == (4, 1, 3)
    assert descriptive_statistics((None,)).median is None
    differences = paired_differences(
        {("a", 1): 2, ("b", 1): None},
        {("a", 1): 5, ("b", 1): 9},
    )
    assert differences == (("a", 1, 3),)
