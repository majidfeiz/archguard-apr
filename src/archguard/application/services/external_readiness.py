"""Deterministic selection, quarantine scanning, review, and readiness policy."""

import hashlib
from dataclasses import replace

from archguard.domain.external_readiness import (
    ExternalReadiness,
    GateStatus,
    OverallReadiness,
    ProfileReviewDecision,
    ProfileReviewState,
    ReadinessGate,
)
from archguard.domain.repository import check

OFFICIAL_PREFIXES = (
    "https://github.com/soarsmu/BugsInPy",
    "https://github.com/SWE-bench/SWE-bench",
    "https://huggingface.co/datasets/SWE-bench/SWE-bench_Verified",
)
PROHIBITED_GOLD_FIELDS = frozenset(
    {"patch", "test_patch", "fixed_revision", "oracle_retrieval", "fail_to_pass", "pass_to_pass"}
)


def require_official_source(url: str) -> None:
    check(
        any(url == prefix or url.startswith(prefix + "/") for prefix in OFFICIAL_PREFIXES),
        "external source is not allowlisted",
    )


def select_candidates(candidate_ids: tuple[str, ...], seed: int, maximum: int) -> tuple[str, ...]:
    check(seed >= 0 and maximum > 0, "invalid selection policy")
    unique = tuple(sorted(set(candidate_ids)))
    ordered = sorted(
        unique, key=lambda item: (hashlib.sha256(f"{seed}:{item}".encode()).hexdigest(), item)
    )
    return tuple(sorted(ordered[:maximum]))


def scan_agent_artifact(value: object, canaries: tuple[str, ...] = ()) -> None:
    rendered = str(value)
    keys = {str(key).lower() for key in value} if isinstance(value, dict) else set()
    check(not (keys & PROHIBITED_GOLD_FIELDS), "gold or evaluator-only field crossed boundary")
    check(
        not any(canary and canary in rendered for canary in canaries),
        "gold canary crossed boundary",
    )


def apply_human_review(
    profile_fingerprint: str, current: ProfileReviewState, review: ProfileReviewDecision
) -> ProfileReviewState:
    check(
        current
        in {
            ProfileReviewState.DRAFT,
            ProfileReviewState.REVIEW_REQUIRED,
            ProfileReviewState.REVISED,
        },
        "profile is not reviewable",
    )
    check(review.profile_fingerprint == profile_fingerprint, "stale or wrong-profile review")
    return review.decision


def freeze_reviewed_profile(
    profile_fingerprint: str, review: ProfileReviewDecision
) -> ProfileReviewState:
    check(review.profile_fingerprint == profile_fingerprint, "stale or wrong-profile review")
    check(review.decision == ProfileReviewState.APPROVED, "only human-approved profile may freeze")
    check(
        not review.rejected_rules and not review.requested_changes, "partial approval cannot freeze"
    )
    return ProfileReviewState.FROZEN


def derive_readiness(gates: tuple[ReadinessGate, ...]) -> ExternalReadiness:
    ordered = tuple(sorted(gates, key=lambda item: item.gate_id))
    mandatory = tuple(item for item in ordered if item.required)
    all_passed = bool(mandatory) and all(item.status == GateStatus.PASSED for item in mandatory)
    human_pending = any(
        item.reviewer_required and item.status != GateStatus.PASSED for item in mandatory
    )
    status = (
        OverallReadiness.FINAL_EVALUATION_READY
        if all_passed
        else OverallReadiness.REVIEW_REQUIRED
        if human_pending
        else OverallReadiness.NOT_READY
    )
    return ExternalReadiness("archguard.external-readiness/v1", ordered, status)


def revise_gate(gate: ReadinessGate, status: GateStatus, blocker: str | None) -> ReadinessGate:
    return replace(gate, status=status, blocker_reason=blocker, evidence=())
