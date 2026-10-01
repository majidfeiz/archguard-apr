import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from archguard.application.services.external_readiness import (
    apply_human_review,
    derive_readiness,
    freeze_reviewed_profile,
    require_official_source,
    scan_agent_artifact,
    select_candidates,
)
from archguard.domain.external_readiness import (
    PROFILE_REVIEW_SCHEMA,
    AcquisitionRecord,
    ExternalReadiness,
    GateStatus,
    LicenseRecord,
    OverallReadiness,
    ProfileReviewDecision,
    ProfileReviewState,
    QualificationStage,
    ReadinessGate,
    ReproductionRecord,
    Stability,
)
from archguard.domain.orchestration import ArtifactReference
from archguard.infrastructure.external_storage import validate_external_root


def ref(char: str = "a") -> ArtifactReference:
    return ArtifactReference("readiness_evidence", char * 64)


def gate(
    identifier: str,
    status: GateStatus = GateStatus.BLOCKED,
    reviewer: bool = False,
) -> ReadinessGate:
    return ReadinessGate(
        identifier,
        QualificationStage.HUMAN_REVIEW if reviewer else QualificationStage.METADATA,
        True,
        status,
        (ref(),) if status == GateStatus.PASSED else (),
        None if status == GateStatus.PASSED else "not yet qualified",
        reviewer,
        "linux-x86_64" if identifier == "platform" else None,
        "supply independently verified evidence",
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/soarsmu/BugsInPy",
        "https://github.com/SWE-bench/SWE-bench/tree/main",
        "https://huggingface.co/datasets/SWE-bench/SWE-bench_Verified",
    ],
)
def test_only_official_sources_are_allowed(url: str) -> None:
    require_official_source(url)
    with pytest.raises(ValueError, match="allowlisted"):
        require_official_source("https://example.invalid/copy")


def test_candidate_selection_is_seeded_stable_and_bounded() -> None:
    candidates = ("p-3", "p-1", "p-2", "p-1")
    assert select_candidates(candidates, 125, 2) == select_candidates(
        tuple(reversed(candidates)), 125, 2
    )
    assert len(select_candidates(candidates, 125, 2)) == 2


def test_acquisition_record_rejects_mutable_or_corrupt_identity() -> None:
    record = AcquisitionRecord(
        "official-framework",
        "https://github.com/SWE-bench/SWE-bench",
        "a" * 40,
        "a" * 40,
        "b" * 64,
        "git clone --no-checkout with hooks disabled",
        123,
        "AGENT_VISIBLE",
        True,
    )
    assert record.complete and record.byte_size == 123
    with pytest.raises(ValueError, match="revision mismatch"):
        replace(record, observed_revision="c" * 40)
    with pytest.raises(ValueError, match="SHA-256"):
        replace(record, content_sha256="corrupt")


def test_license_resolution_is_explicit_and_per_subject() -> None:
    verified = LicenseRecord(
        "swe-bench-framework",
        "MIT",
        "https://github.com/SWE-bench/SWE-bench/blob/02e7a74/LICENSE",
        "02e7a74ffd0b707aab73d203fe87bdc7c76afc8e",
        "allowed",
        "retain notice",
        "allowed",
        "metadata-only",
        None,
    )
    unresolved = LicenseRecord(
        "bugsinpy-framework",
        None,
        "https://github.com/soarsmu/BugsInPy/tree/11c5f1e",
        "11c5f1eea954a42132cfd06bf257766a7963e0fd",
        "unresolved",
        "unresolved",
        "unresolved",
        "metadata-only",
        "No authoritative license file found.",
    )
    assert verified.subject_id != unresolved.subject_id and unresolved.identifier is None
    with pytest.raises(ValueError, match="resolution"):
        replace(unresolved, identifier="MIT")


def test_external_storage_rejects_repository_and_symlink(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    with pytest.raises(ValueError, match="inside"):
        validate_external_root(repository / "cache", repository)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "link"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        validate_external_root(link, repository)
    assert validate_external_root(outside, repository) == outside.resolve()


@pytest.mark.parametrize(
    "field",
    ["patch", "test_patch", "fixed_revision", "oracle_retrieval", "FAIL_TO_PASS", "PASS_TO_PASS"],
)
def test_gold_fields_and_canaries_are_rejected_everywhere(field: str) -> None:
    with pytest.raises(ValueError, match="boundary"):
        scan_agent_artifact({field: "secret"})
    with pytest.raises(ValueError, match="canary"):
        scan_agent_artifact({"event": "READINESS-GOLD-CANARY"}, ("READINESS-GOLD-CANARY",))


def review(decision: ProfileReviewState = ProfileReviewState.APPROVED) -> ProfileReviewDecision:
    return ProfileReviewDecision(
        PROFILE_REVIEW_SCHEMA,
        "b" * 64,
        "external-reviewer-id",
        "2026-10-01",
        decision,
        "Reviewed outside automated generation.",
        ("rule-1",),
        (),
        (),
    )


def test_human_review_must_match_and_partial_review_cannot_freeze() -> None:
    assert (
        apply_human_review("b" * 64, ProfileReviewState.REVIEW_REQUIRED, review())
        == ProfileReviewState.APPROVED
    )
    assert freeze_reviewed_profile("b" * 64, review()) == ProfileReviewState.FROZEN
    with pytest.raises(ValueError, match="wrong-profile"):
        apply_human_review("c" * 64, ProfileReviewState.DRAFT, review())
    with pytest.raises(ValueError, match="partial"):
        freeze_reviewed_profile("b" * 64, replace(review(), requested_changes=("revise",)))


def test_readiness_cannot_be_forged_and_requires_human_linux_evidence() -> None:
    blocked = derive_readiness((gate("license"), gate("profiles", reviewer=True), gate("platform")))
    assert blocked.overall_status == OverallReadiness.REVIEW_REQUIRED
    passed = derive_readiness(
        (
            gate("license", GateStatus.PASSED),
            gate("profiles", GateStatus.PASSED, True),
            gate("platform", GateStatus.PASSED),
        )
    )
    assert passed.overall_status == OverallReadiness.FINAL_EVALUATION_READY
    with pytest.raises(ValueError, match="forged"):
        ExternalReadiness(blocked.schema, blocked.gates, OverallReadiness.FINAL_EVALUATION_READY)


def test_reproduction_requires_repeated_consistent_observations() -> None:
    value = ReproductionRecord(
        "task-1",
        ("expected-failure", "expected-failure"),
        Stability.STABLE,
        True,
        True,
        "linux-x86_64",
    )
    assert json.loads(json.dumps(asdict(value)))["stability"] == "STABLE"
    with pytest.raises(ValueError, match="contradicts"):
        replace(value, attempts=("pass", "fail"))
