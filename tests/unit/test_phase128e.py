import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from archguard.domain.phase128e import (
    AuditStatus,
    CandidateRecord,
    LicenseRecord,
    reject_outcome_fields,
    select_preparation_pool,
)
from archguard.infrastructure.phase128e_records import validate_tracked_records


@pytest.fixture
def records(repository_root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    return validate_tracked_records(repository_root)


def test_license_evidence_is_immutable_and_scopes_are_separate(
    records: tuple[dict[str, Any], dict[str, Any], dict[str, Any]],
) -> None:
    licenses, _, _ = records
    items = {item["subject_id"]: item for item in licenses["records"]}
    assert len({item["subject_kind"] for item in items.values()}) == 3
    assert all(item["immutable_locator"] for item in items.values())
    assert items["bugsinpy-framework"]["audit_status"] == "UNRESOLVED"
    assert items["bugsinpy-framework"]["spdx_identifier"] is None
    assert items["swe-bench-verified-dataset"]["audit_status"] == "UNRESOLVED"
    assert items["swe-bench-framework"]["audit_status"] == "VERIFIED"


def test_absent_license_and_invalid_spdx_inference_are_rejected() -> None:
    base: dict[str, Any] = dict(
        subject_id="missing",
        subject_kind="project",
        official_source_url="https://github.com/example/project",
        immutable_locator="a" * 40,
        license_file_path=None,
        license_sha256=None,
        redistribution_status=AuditStatus.UNRESOLVED,
        benchmark_use_status=AuditStatus.UNRESOLVED,
        source_execution_status=AuditStatus.UNRESOLVED,
        evidence_timestamp="2026-10-07T00:00:00Z",
        evidence_type="tree inspection",
        reason="No license file.",
        limitations=("Not legal advice.",),
    )
    record = LicenseRecord(spdx_identifier=None, audit_status=AuditStatus.UNRESOLVED, **base)
    assert record.audit_status is AuditStatus.UNRESOLVED
    with pytest.raises(ValueError, match="cannot infer SPDX"):
        LicenseRecord(spdx_identifier="MIT", audit_status=AuditStatus.UNRESOLVED, **base)
    with pytest.raises(ValueError, match="VERIFIED requires"):
        LicenseRecord(spdx_identifier=None, audit_status=AuditStatus.VERIFIED, **base)


def test_outcome_blind_selection_rejects_hidden_answer_fields() -> None:
    for key in ("gold_patch", "reference_patch", "repair_success", "benchmark_score"):
        with pytest.raises(ValueError, match="prohibited"):
            reject_outcome_fields({"nested": [{key: "hidden"}]})


def test_selection_is_deterministic_stratified_and_capped(
    records: tuple[dict[str, Any], dict[str, Any], dict[str, Any]],
) -> None:
    _, pool, _ = records
    candidates = tuple(CandidateRecord(**item) for item in pool["observed"])
    first = select_preparation_pool(candidates)
    second = select_preparation_pool(tuple(reversed(candidates)))
    assert [item.task_id for item in first] == [item.task_id for item in second]
    assert [item.task_id for item in first] == pool["selected_identifiers"]
    assert len({item.project for item in first}) == 3
    assert (
        max(
            sum(item.project == project for item in first) for project in {i.project for i in first}
        )
        <= 4
    )
    assert all(item.eligible and not item.unsupported_gitlink for item in first)


def test_unresolved_project_license_cannot_be_eligible(
    records: tuple[dict[str, Any], dict[str, Any], dict[str, Any]],
) -> None:
    licenses, pool, _ = records
    verified = {
        item["subject_id"] for item in licenses["records"] if item["audit_status"] == "VERIFIED"
    }
    assert all(
        (not item["eligible"]) or item["license_record"] in verified for item in pool["observed"]
    )


def test_exact_revisions_and_stable_registry_fingerprint(
    records: tuple[dict[str, Any], dict[str, Any], dict[str, Any]],
) -> None:
    _, pool, _ = records
    assert all(
        len(item[key]) == 40 and set(item[key]) <= set("0123456789abcdef")
        for item in pool["observed"]
        for key in ("source_revision", "buggy_revision", "fixed_revision")
    )
    assert pool["fingerprint"] == "d1068112a12c63e24ee780ad9b31b05c04f9b1417efa50ffa04a1b8b4aac1903"


def test_no_evaluator_execution_fields_and_readiness_stays_false(
    records: tuple[dict[str, Any], dict[str, Any], dict[str, Any]],
) -> None:
    _, pool, _ = records
    assert pool["phase_13_ready"] is False
    assert pool["final_pilot_list_frozen"] is False
    assert all(item["repetitions"] == 3 for item in pool["observed"])
    assert "execution_result" not in json.dumps(pool)


def test_frozen_profile_and_protocol_history_are_preserved(repository_root: Path) -> None:
    expected = {
        "research/profiles/pysnooper-profile-freeze.json": (
            "345b134bfb1f3e3faf6a8fe08b9edb870b92c25242e9f86edbcb3344a78d91f3"
        ),
        "configs/external-profiles/pysnooper-micro-pilot-amended-v2.yaml": (
            "d7215e09aabd6724883ea84f778406a7c53dff79b9f05f2914cb54242381f7ed"
        ),
        "research/reviews/pysnooper-profile-decision.json": (
            "47caf830435e4649719dafaf46d533d0f6b84449b369a1908241eec755df70f4"
        ),
        "research/reviews/protocol-decision-history-v1.json": (
            "bc19d920338354298eee6f7582e597a7e17929a93067b5a9c603b4edc00621a7"
        ),
    }
    for name, digest in expected.items():
        assert hashlib.sha256((repository_root / name).read_bytes()).hexdigest() == digest


def test_ineligible_candidate_cannot_be_silently_flipped(
    records: tuple[dict[str, Any], dict[str, Any], dict[str, Any]],
) -> None:
    _, pool, _ = records
    source = next(item for item in pool["observed"] if item["ineligible_reason"])
    candidate = CandidateRecord(**source)
    with pytest.raises(ValueError, match="eligibility contradiction|unsupported"):
        dataclasses.replace(candidate, eligible=True, ineligible_reason=None)
