from dataclasses import replace

import pytest

from archguard.application.services.repair_loop import (
    add_candidate,
    precheck,
    replay,
    select,
    transition,
)
from archguard.domain.orchestration import AgentRole, ArtifactReference
from archguard.domain.repair import (
    LINEAGE_SCHEMA,
    PATCH_CANDIDATE_SCHEMA,
    REPAIR_TASK_SCHEMA,
    AcceptancePolicy,
    CandidateLineage,
    PatchCandidate,
    PatchPolicy,
    PrecheckCode,
    RepairBudget,
    RepairIntent,
    RepairLoopState,
    RepairTask,
    ValidationEvidence,
    forbidden_change,
    normalized_patch,
    patch_stats,
    path_allowed,
    rank_validated,
    raw_fingerprint,
    semantic_candidate_fingerprint,
)
from archguard.infrastructure.patch_inspector import UnifiedDiffInspector

PATCH = b"""diff --git a/src/demo.py b/src/demo.py
--- a/src/demo.py
+++ b/src/demo.py
@@ -1 +1 @@
-return 1
+return 2
"""


def ref(kind: str, char: str) -> ArtifactReference:
    return ArtifactReference(kind, char * 64)


def task(**changes: object) -> RepairTask:
    values = dict(
        schema=REPAIR_TASK_SCHEMA,
        task_id="task",
        repository="fixture",
        baseline_revision="a" * 40,
        problem_statement="untrusted issue text",
        failing_tests=("test_x",),
        target_tests=("test_x",),
        regression_scope=("tests",),
        architecture_profile=ref("profile", "1"),
        repository_graph=ref("graph", "2"),
        execution_plan=ref("plan", "3"),
        patch_policy=PatchPolicy(("src/**",), protected_paths=("src/protected.py",)),
        budget=RepairBudget(3, 2, 5, 5, 5, 100, 100),
        provider_policy="offline",
        diversity_intents=("minimal_local_fix",),
        acceptance=AcceptancePolicy(first_success=True),
        human_approval_required=False,
    )
    values.update(changes)
    return RepairTask(**values)  # type: ignore[arg-type]


def candidate(
    identifier: str, patch: bytes = PATCH, parent: str | None = None, round_: int = 1
) -> PatchCandidate:
    normalized = normalized_patch(patch)
    patch_hash = raw_fingerprint(normalized)
    paths = ("src/demo.py",)
    return PatchCandidate(
        PATCH_CANDIDATE_SCHEMA,
        identifier,
        "run",
        task().task_fingerprint,
        round_,
        parent,
        AgentRole.PATCH_PROPOSER,
        ref("invocation", "4"),
        ref("patch", "5"),
        patch_hash,
        semantic_candidate_fingerprint(task().task_fingerprint, patch_hash, paths),
        paths,
        1,
        1,
        RepairIntent.MINIMAL_LOCAL_FIX,
        (),
    )


def evidence(identifier: str, **changes: object) -> ValidationEvidence:
    values = dict(
        candidate_id=identifier,
        applicable=True,
        analysis_complete=True,
        architecture_passed=True,
        introduced_architecture_errors=0,
        regressions=0,
        target_failures_fixed=1,
        persistent_failures=0,
        required_tests_preserved=True,
        timed_out=False,
        infrastructure_failure=False,
        cleanup_succeeded=True,
        patch_bytes=100,
        changed_files=1,
    )
    values.update(changes)
    return ValidationEvidence(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "changes",
    [
        {"schema": "bad"},
        {"baseline_revision": "bad"},
        {"repository": "../escape"},
        {"mandatory_validation": False},
        {"trust_model_evidence": True},
        {"provider_policy": ""},
    ],
)
def test_task_rejects_invalid(changes: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        task(**changes)


def test_policy_and_budget_reject_contradictions() -> None:
    with pytest.raises(ValueError):
        RepairBudget(1, 3, 2, 1, 1, 1, 1)
    with pytest.raises(ValueError):
        PatchPolicy(("src/**",), protected_paths=("src/**",))
    with pytest.raises(ValueError):
        AcceptancePolicy(require_no_regressions=False)


@pytest.mark.parametrize(
    "raw",
    [b"prose\n" + PATCH, b"```diff\n" + PATCH + b"```\n", PATCH + b"\0", b"\xff"],
)
def test_patch_normalization_fails_closed(raw: bytes) -> None:
    with pytest.raises(ValueError):
        normalized_patch(raw)


def test_patch_normalization_and_stats_are_stable() -> None:
    windows = PATCH.replace(b"\n", b"\r\n")
    assert normalized_patch(windows) == normalized_patch(PATCH)
    assert patch_stats(PATCH) == (1, 1)


@pytest.mark.parametrize(
    "path,allowed",
    [
        ("src/demo.py", True),
        ("tests/test_demo.py", False),
        ("uv.lock", False),
        ("src/protected.py", False),
    ],
)
def test_protected_path_policy(path: str, allowed: bool) -> None:
    assert path_allowed(path, task().patch_policy) is allowed


@pytest.mark.parametrize(
    "payload",
    [
        b"+@pytest.mark.skip",
        b"+pytest.skip('x')",
        b"+assert True",
        b"+privileged: true",
        b"+cmd || true",
    ],
)
def test_forbidden_validation_changes(payload: bytes) -> None:
    assert forbidden_change(payload)


def test_precheck_accepts_safe_and_rejects_duplicate() -> None:
    value = candidate("candidate-a")
    parsed = UnifiedDiffInspector().inspect(PATCH)
    empty = CandidateLineage(LINEAGE_SCHEMA, "run", ())
    assert precheck(task(), PATCH, parsed, value, empty).accepted
    lineage = add_candidate(empty, value)
    duplicate = replace(
        candidate("candidate-b"),
        semantic_candidate_fingerprint=value.semantic_candidate_fingerprint,
    )
    result = precheck(task(), PATCH, parsed, duplicate, lineage)
    assert PrecheckCode.DUPLICATE in result.reasons


def test_lineage_parent_child_duplicate_and_rejections() -> None:
    first = candidate("a")
    lineage = add_candidate(CandidateLineage(LINEAGE_SCHEMA, "run", ()), first)
    second = candidate("b", parent="a", round_=2)
    lineage = add_candidate(lineage, second)
    assert lineage.duplicates == (("b", "a"),)
    with pytest.raises(ValueError, match="missing"):
        CandidateLineage(LINEAGE_SCHEMA, "run", (candidate("c", parent="missing", round_=2),))
    with pytest.raises(ValueError, match="cross-run"):
        CandidateLineage(LINEAGE_SCHEMA, "other", (first,))


def test_state_machine_and_replay_are_deterministic() -> None:
    events = transition((), RepairLoopState.TASK_VALIDATED, "valid")
    events = transition(events, RepairLoopState.CONTEXT_PREPARED, "context")
    events = transition(events, RepairLoopState.ROUND_STARTED, "round-1")
    assert replay(events) == RepairLoopState.ROUND_STARTED
    with pytest.raises(ValueError, match="illegal"):
        transition(events, RepairLoopState.COMPLETED, "skip")
    terminal = transition(events, RepairLoopState.CANCELLED, "human")
    with pytest.raises(ValueError, match="terminal"):
        transition(terminal, RepairLoopState.COMPLETED, "late")


def test_ranking_uses_evidence_not_model_identity() -> None:
    large = candidate("large")
    small = replace(candidate("small"), repair_round=2)
    ranked = rank_validated(
        ((large, evidence("large", patch_bytes=200)), (small, evidence("small", patch_bytes=50))),
        task().acceptance,
    )
    assert ranked == ("small", "large")
    assert (
        select(task(), ((large, evidence("large", regressions=1)), (small, evidence("small"))))
        == "small"
    )
    assert not evidence("bad", regressions=1).accepted(task().acceptance)
