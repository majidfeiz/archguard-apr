from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from archguard.domain.phase128a import (
    GRAPH_SCHEMA,
    LICENSE_SCHEMA,
    Candidate,
    GraphEvidence,
    LicenseEvidence,
    LicenseStatus,
    LicenseSubject,
    exact_mcnemar_power,
    select_pilot,
)
from archguard.infrastructure.phase128a_artifacts import validate_phase128a_artifacts

GIT_A = "a" * 40
GIT_B = "b" * 40
SHA = "c" * 64


def license_record(**changes: object) -> LicenseEvidence:
    values: dict[str, Any] = {
        "schema": LICENSE_SCHEMA,
        "subject_id": "project-a",
        "subject_kind": LicenseSubject.PROJECT,
        "canonical_url": "https://example.invalid/project-a",
        "revision": GIT_A,
        "license_path": None,
        "license_sha256": None,
        "spdx": None,
        "evidence_method": "immutable metadata",
        "redistribution": LicenseStatus.UNRESOLVED,
        "evaluator_use": LicenseStatus.UNRESOLVED,
        "notes": "No license text was available; remains unresolved.",
    }
    values.update(changes)
    return LicenseEvidence(**values)


def test_license_scope_and_fingerprint_are_explicit() -> None:
    project = license_record()
    framework = license_record(subject_id="framework-a", subject_kind=LicenseSubject.FRAMEWORK)
    assert project.fingerprint != framework.fingerprint
    with pytest.raises(ValueError, match="verified license"):
        license_record(redistribution=LicenseStatus.VERIFIED)
    with pytest.raises(ValueError, match="fingerprint"):
        replace(project, fingerprint=SHA)


def test_graph_evidence_fails_closed_until_complete() -> None:
    pending = GraphEvidence(
        GRAPH_SCHEMA,
        "EXTERNAL_EXECUTION_REQUIRED",
        "project-a",
        GIT_A,
        SHA,
        None,
        None,
        None,
        None,
        None,
        (),
        (),
        None,
        ("external run required",),
    )
    assert pending.status == "EXTERNAL_EXECUTION_REQUIRED"
    with pytest.raises(ValueError, match="incomplete"):
        replace(pending, status="VALIDATED", fingerprint="")


def candidate(project: str, task: str, eligible: bool = True) -> Candidate:
    return Candidate(
        "source",
        project,
        task,
        GIT_A,
        GIT_B,
        f"license-{project}",
        eligible,
        None if eligible else "LICENSE_UNRESOLVED",
    )


def test_selection_is_deterministic_stratified_and_outcome_blind() -> None:
    pool = tuple(
        candidate(project, f"task-{project}-{number}")
        for number in range(3)
        for project in ("a", "b")
    )
    selected = select_pilot(tuple(reversed(pool)))
    assert selected == select_pilot(pool)
    assert [item.project for item in selected[:2]] == ["a", "b"]
    assert len(selected) == 6


def test_ineligible_candidate_is_never_selected_or_replaced() -> None:
    pool = (candidate("a", "task-a", False), candidate("b", "task-b"))
    assert [item.task_id for item in select_pilot(pool)] == ["task-b"]


@pytest.mark.parametrize("n", [20, 30, 50])
def test_power_analysis_is_deterministic(n: int) -> None:
    assert exact_mcnemar_power(n, 0.5, 0.75) == exact_mcnemar_power(n, 0.5, 0.75)


@pytest.mark.parametrize("args", [(0, 0.5, 0.75), (20, 0.0, 0.75), (20, 0.5, 0.5)])
def test_power_analysis_rejects_invalid_assumptions(args: tuple[int, float, float]) -> None:
    with pytest.raises(ValueError):
        exact_mcnemar_power(*args)


def test_tracked_phase128a_artifacts_are_fingerprint_bound(repository_root: Path) -> None:
    result = validate_phase128a_artifacts(repository_root / "research")
    assert result["artifact_count"] == 6
