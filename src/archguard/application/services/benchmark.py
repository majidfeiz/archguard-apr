"""Deterministic benchmark policies with no network, source, or evaluator access."""

import hashlib

from archguard.domain.benchmark import (
    SPLIT_SCHEMA,
    BenchmarkTask,
    ContaminationRisk,
    DatasetSplit,
    EligibilityEvidence,
    EligibilityResult,
    ExclusionReason,
    LeakageAssessment,
    SplitManifest,
    TaskState,
)

TRANSITIONS = {
    TaskState.DISCOVERED: {TaskState.METADATA_VALIDATED, TaskState.EXCLUDED, TaskState.QUARANTINED},
    TaskState.METADATA_VALIDATED: {TaskState.ACQUIRED, TaskState.EXCLUDED, TaskState.QUARANTINED},
    TaskState.ACQUIRED: {TaskState.INTEGRITY_VERIFIED, TaskState.EXCLUDED, TaskState.QUARANTINED},
    TaskState.INTEGRITY_VERIFIED: {
        TaskState.ENVIRONMENT_READY,
        TaskState.EXCLUDED,
        TaskState.QUARANTINED,
    },
    TaskState.ENVIRONMENT_READY: {TaskState.BUG_REPRODUCED, TaskState.EXCLUDED},
    TaskState.BUG_REPRODUCED: {TaskState.ARCHITECTURE_ANALYZED, TaskState.EXCLUDED},
    TaskState.ARCHITECTURE_ANALYZED: {TaskState.ELIGIBLE, TaskState.EXCLUDED},
    TaskState.ELIGIBLE: {TaskState.DRY_RUN_VERIFIED, TaskState.EXCLUDED},
}


def require_transition(current: TaskState, target: TaskState) -> None:
    if target not in TRANSITIONS.get(current, set()):
        raise ValueError("illegal benchmark task transition")


def evaluate_eligibility(evidence: EligibilityEvidence) -> EligibilityResult:
    checks = (
        (evidence.source_available, ExclusionReason.SOURCE_UNAVAILABLE),
        (evidence.revision_available, ExclusionReason.REVISION_UNAVAILABLE),
        (evidence.licensed, ExclusionReason.MISSING_LICENSE),
        (evidence.environment_ready, ExclusionReason.BUILD_FAILURE),
        (evidence.target_failure_reproduced, ExclusionReason.TARGET_FAILURE_NOT_REPRODUCED),
        (evidence.deterministic_baseline, ExclusionReason.NONDETERMINISTIC_BASELINE),
        (evidence.architecture_analyzed, ExclusionReason.ANALYSIS_FAILURE),
        (evidence.graph_constructed, ExclusionReason.GRAPH_FAILURE),
        (evidence.evaluator_ready, ExclusionReason.EVALUATOR_FAILURE),
        (evidence.gold_isolated, ExclusionReason.GOLD_ISOLATION_FAILURE),
        (evidence.supported_platform, ExclusionReason.UNSUPPORTED_PLATFORM),
        (evidence.no_external_service, ExclusionReason.EXTERNAL_SERVICE_REQUIRED),
        (evidence.within_resources, ExclusionReason.RESOURCE_LIMIT_EXCEEDED),
    )
    reasons = tuple(reason for passed, reason in checks if not passed)
    return EligibilityResult(evidence.task_id, not reasons, reasons)


def create_splits(
    tasks: tuple[BenchmarkTask, ...], seed: int, version: int = 1, frozen: bool = False
) -> SplitManifest:
    groups: dict[str, list[BenchmarkTask]] = {}
    for task in tasks:
        groups.setdefault(task.project_id, []).append(task)
    assignments: list[tuple[str, DatasetSplit]] = []
    for project, members in sorted(groups.items()):
        bucket = int(hashlib.sha256(f"{seed}:{project}".encode()).hexdigest()[:8], 16) % 10
        split = (
            DatasetSplit.DEVELOPMENT
            if bucket < 6
            else DatasetSplit.PILOT
            if bucket < 8
            else DatasetSplit.EVALUATION
        )
        for task in sorted(members, key=lambda item: item.task_id):
            assignments.append(
                (task.task_id, DatasetSplit.EXCLUDED if task.state == TaskState.EXCLUDED else split)
            )
    return SplitManifest(SPLIT_SCHEMA, version, seed, tuple(sorted(assignments)), "project", frozen)


def select_pilot(tasks: tuple[BenchmarkTask, ...], seed: int, maximum: int) -> tuple[str, ...]:
    eligible = [
        task
        for task in tasks
        if task.state in {TaskState.ELIGIBLE, TaskState.DRY_RUN_VERIFIED}
        and task.split == DatasetSplit.PILOT
    ]
    eligible.sort(
        key=lambda task: (
            hashlib.sha256(f"{seed}:{task.project_id}:{task.task_id}".encode()).hexdigest(),
            task.task_id,
        )
    )
    selected: list[BenchmarkTask] = []
    used_projects: set[str] = set()
    for task in eligible:
        if task.project_id not in used_projects:
            selected.append(task)
            used_projects.add(task.project_id)
        if len(selected) == maximum:
            break
    for task in eligible:
        if len(selected) == maximum:
            break
        if task not in selected:
            selected.append(task)
    return tuple(sorted(task.task_id for task in selected))


def audit_text(
    task_id: str, issue_text: str, gold_canary: str | None, oracle_available: bool
) -> LeakageAssessment:
    signals: list[str] = []
    lowered = issue_text.lower()
    if any(
        token in lowered for token in ("apply this patch", "diff --git", "the fix is", "solution:")
    ):
        signals.append("issue_solution_signal")
    if gold_canary and gold_canary in issue_text:
        signals.append("gold_canary_detected")
    if oracle_available:
        signals.append("oracle_retrieval_exists")
    risk = (
        ContaminationRisk.HIGH
        if "gold_canary_detected" in signals
        else ContaminationRisk.MEDIUM
        if signals
        else ContaminationRisk.UNKNOWN
    )
    return LeakageAssessment(task_id, tuple(sorted(signals)), risk, risk == ContaminationRisk.HIGH)


def assert_agent_visible(record: dict[str, object], gold_canaries: tuple[str, ...] = ()) -> None:
    prohibited = {
        "patch",
        "test_patch",
        "fixed_revision",
        "gold_patch",
        "oracle_retrieval",
        "fail_to_pass",
        "pass_to_pass",
    }
    if prohibited & {key.lower() for key in record}:
        raise ValueError("evaluator-only or gold field crossed agent boundary")
    rendered = str(record)
    if any(canary and canary in rendered for canary in gold_canaries):
        raise ValueError("gold canary crossed agent boundary")
