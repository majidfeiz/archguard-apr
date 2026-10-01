import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from archguard.application.services.benchmark import (
    assert_agent_visible,
    audit_text,
    create_splits,
    evaluate_eligibility,
    require_transition,
    select_pilot,
)
from archguard.domain.benchmark import (
    LEAKAGE_SCHEMA,
    REGISTRY_SCHEMA,
    SNAPSHOT_SCHEMA,
    SPLIT_SCHEMA,
    TASK_SCHEMA,
    AcquisitionPolicy,
    BenchmarkKind,
    BenchmarkRegistry,
    BenchmarkRegistryEntry,
    BenchmarkSnapshot,
    BenchmarkTask,
    ContaminationRisk,
    DatasetSplit,
    EligibilityEvidence,
    ExclusionReason,
    LeakageAudit,
    ProfileRecord,
    ProfileState,
    SplitManifest,
    TaskState,
)
from archguard.domain.orchestration import ArtifactReference
from archguard.infrastructure.benchmark import CACHE_MARKER, load_registry, verify_cache


def ref(kind: str, char: str) -> ArtifactReference:
    return ArtifactReference(kind, char * 64)


def entry(identifier: str = "fixture") -> BenchmarkRegistryEntry:
    return BenchmarkRegistryEntry(
        identifier,
        BenchmarkKind.SYNTHETIC,
        "1",
        "https://example.invalid/fixture",
        "a" * 40,
        "Controlled fixture citation",
        "Apache-2.0",
        "https://example.invalid/license",
        "allowed",
        "1",
        1,
        ("python",),
        ("arm64", "x86_64"),
        AcquisitionPolicy.OFFLINE_CACHE_ONLY,
        "sha256",
        "quarantined",
        "atomic_offline",
        "trusted_source_free",
        ("fixture_only",),
    )


def task(
    identifier: str = "task-a",
    project: str = "project-a",
    state: TaskState = TaskState.ELIGIBLE,
    split: DatasetSplit = DatasetSplit.PILOT,
) -> BenchmarkTask:
    reasons = (ExclusionReason.POLICY_EXCLUSION,) if state == TaskState.EXCLUDED else ()
    return BenchmarkTask(
        TASK_SCHEMA,
        identifier,
        "fixture",
        project,
        identifier,
        "python",
        "https://example.invalid/repository",
        "b" * 40,
        ref("problem", "1"),
        ("tests/test_fixture.py::test_bug",),
        (ref("evaluator_tests", "2"),),
        ref("environment", "3"),
        ref("profile", "4"),
        state,
        reasons,
        "Apache-2.0",
        (("source", "controlled_fixture"),),
        ("5" * 64,),
        split,
        "agent_visible",
        fixed_revision_hash="6" * 64,
        gold_patch_hash="7" * 64,
    )


def evidence(**changes: bool) -> EligibilityEvidence:
    values: dict[str, object] = {
        "task_id": "task-a",
        "source_available": True,
        "revision_available": True,
        "licensed": True,
        "environment_ready": True,
        "target_failure_reproduced": True,
        "deterministic_baseline": True,
        "architecture_analyzed": True,
        "graph_constructed": True,
        "evaluator_ready": True,
        "gold_isolated": True,
        "supported_platform": True,
        "no_external_service": True,
        "within_resources": True,
    }
    values.update(changes)
    return EligibilityEvidence(**values)  # type: ignore[arg-type]


def test_registry_is_canonical_and_versioned() -> None:
    registry = BenchmarkRegistry(REGISTRY_SCHEMA, (entry(),))
    assert len(registry.registry_fingerprint) == 64
    with pytest.raises(ValueError, match="unsupported"):
        replace(registry, schema="bad", registry_fingerprint="")
    with pytest.raises(ValueError, match="duplicate"):
        BenchmarkRegistry(REGISTRY_SCHEMA, (entry(), entry()))


@pytest.mark.parametrize(
    "change",
    [
        {"upstream_revision": "main"},
        {"license_identifier": ""},
        {"redistribution_status": "maybe"},
        {"supported_languages": ("python", "java")},
    ],
)
def test_registry_entry_rejects_invalid(change: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        replace(entry(), **change)


def test_task_exclusion_is_explicit_and_hash_stable() -> None:
    one = task()
    two = task()
    assert one.task_fingerprint == two.task_fingerprint
    with pytest.raises(ValueError, match="exclusion"):
        replace(one, state=TaskState.EXCLUDED, task_fingerprint="")


def test_state_transitions_reject_skips() -> None:
    require_transition(TaskState.DISCOVERED, TaskState.METADATA_VALIDATED)
    with pytest.raises(ValueError, match="illegal"):
        require_transition(TaskState.DISCOVERED, TaskState.ELIGIBLE)


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"environment_ready": False}, ExclusionReason.BUILD_FAILURE),
        ({"target_failure_reproduced": False}, ExclusionReason.TARGET_FAILURE_NOT_REPRODUCED),
        ({"deterministic_baseline": False}, ExclusionReason.NONDETERMINISTIC_BASELINE),
        ({"gold_isolated": False}, ExclusionReason.GOLD_ISOLATION_FAILURE),
        ({"supported_platform": False}, ExclusionReason.UNSUPPORTED_PLATFORM),
    ],
)
def test_eligibility_retains_reasons(change: dict[str, bool], reason: ExclusionReason) -> None:
    result = evaluate_eligibility(evidence(**change))
    assert not result.eligible and reason in result.reasons
    assert evaluate_eligibility(evidence()).eligible


def test_project_grouped_splits_are_deterministic() -> None:
    tasks = (task("a", "same"), task("b", "same"), task("c", "other"))
    one = create_splits(tasks, 17)
    two = create_splits(tuple(reversed(tasks)), 17)
    assert one == two
    mapping = dict(one.assignments)
    assert mapping["a"] == mapping["b"]
    with pytest.raises(ValueError, match="unordered"):
        SplitManifest(SPLIT_SCHEMA, 1, 1, tuple(reversed(one.assignments)), "project", False)


def test_pilot_selection_is_seeded_and_project_stratified() -> None:
    tasks = (task("a", "one"), task("b", "one"), task("c", "two"))
    assert select_pilot(tasks, 7, 2) == select_pilot(tuple(reversed(tasks)), 7, 2)
    assert len(select_pilot(tasks, 7, 2)) == 2


def test_gold_fields_and_canaries_fail_closed() -> None:
    assert_agent_visible({"problem_statement": "public issue"}, ("GOLD-CANARY",))
    for field in ("patch", "test_patch", "FAIL_TO_PASS", "oracle_retrieval"):
        with pytest.raises(ValueError, match="boundary"):
            assert_agent_visible({field: "secret"})
    with pytest.raises(ValueError, match="canary"):
        assert_agent_visible({"problem_statement": "GOLD-CANARY"}, ("GOLD-CANARY",))


def test_contamination_assessment_is_risk_not_proof() -> None:
    high = audit_text("task", "GOLD-CANARY", "GOLD-CANARY", False)
    medium = audit_text("task", "The fix is to change x", None, True)
    assert high.risk == ContaminationRisk.HIGH and high.excluded
    assert medium.risk == ContaminationRisk.MEDIUM
    audit = LeakageAudit(LEAKAGE_SCHEMA, (high,))
    assert len(audit.audit_fingerprint) == 64


def test_snapshot_identity_excludes_location_and_time() -> None:
    profile = ProfileRecord(
        "task-a",
        ref("profile", "4"),
        ProfileState.FROZEN,
        "author",
        "reviewer",
        "Fixture package boundary",
        3,
        0,
    )
    values = (
        SNAPSHOT_SCHEMA,
        "1",
        "a" * 40,
        "fixture-v1",
        (task(),),
        (profile,),
        ref("splits", "8"),
        ref("exclusions", "9"),
        ref("licenses", "a"),
    )
    one = BenchmarkSnapshot(*values)
    two = BenchmarkSnapshot(*values)
    assert one.snapshot_fingerprint == two.snapshot_fingerprint


def test_cache_integrity_and_corruption(tmp_path: Path) -> None:
    payload = tmp_path / "metadata.json"
    payload.write_text("{}")
    marker = {
        "schema": "archguard.benchmark-cache/v1",
        "files": [
            {"path": "metadata.json", "sha256": hashlib.sha256(payload.read_bytes()).hexdigest()}
        ],
    }
    (tmp_path / CACHE_MARKER).write_text(json.dumps(marker))
    assert verify_cache(tmp_path)["status"] == "verified"
    payload.write_text("altered")
    with pytest.raises(ValueError, match="checksum"):
        verify_cache(tmp_path)


@pytest.mark.parametrize(
    "marker",
    [
        None,
        {"schema": "archguard.benchmark-cache/v1", "files": []},
        {
            "schema": "archguard.benchmark-cache/v1",
            "files": [{"path": "../escape", "sha256": "0" * 64}],
        },
    ],
)
def test_partial_and_unsafe_cache_is_rejected(
    tmp_path: Path, marker: dict[str, object] | None
) -> None:
    if marker is not None:
        (tmp_path / CACHE_MARKER).write_text(json.dumps(marker))
        if marker["files"] == []:
            assert verify_cache(tmp_path)["file_count"] == 0
            return
    with pytest.raises(ValueError):
        verify_cache(tmp_path)


@pytest.mark.parametrize("container", ["provider_request", "event_log", "feedback", "output"])
def test_gold_canary_scans_every_agent_output(container: str) -> None:
    with pytest.raises(ValueError, match="canary"):
        assert_agent_visible({container: "ARCHGUARD_GOLD_CANARY"}, ("ARCHGUARD_GOLD_CANARY",))


def test_fixture_registry_loads(repository_root: Path) -> None:
    registry = load_registry(repository_root / "configs/benchmarks.fixture.yaml")
    assert registry.entries[0].kind == BenchmarkKind.SYNTHETIC
