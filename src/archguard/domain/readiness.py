"""Phase 12.8 source-free qualification, review, and readiness contracts."""

import re
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from archguard.domain.orchestration import fingerprint
from archguard.domain.repository import check, digest

EVIDENCE_SCHEMA = "archguard.phase-12.7-x86-qualification/v1"
IMPORTED_EVIDENCE_SCHEMA = "archguard.phase-12.7-x86-qualification-import/v1"
DECISION_SCHEMA = "archguard.human-decision/v1"
PROTOCOL_SCHEMA = "archguard.confirmatory-protocol/v1"
READINESS_SCHEMA = "archguard.phase-13-readiness/v1"


class HumanDecision(StrEnum):
    PENDING = "PENDING"
    APPROVE = "APPROVE"
    REQUEST_CHANGES = "REQUEST_CHANGES"
    REJECT = "REJECT"


@dataclass(frozen=True)
class HumanDecisionRecord:
    schema: str
    subject_kind: str
    reviewed_fingerprint: str
    reviewer_name: str
    review_timestamp: str
    decision: HumanDecision
    checklist: dict[str, bool]
    comments: str

    def __post_init__(self) -> None:
        check(self.schema == DECISION_SCHEMA, "unsupported human decision schema")
        check(
            self.subject_kind in {"architecture_profile", "confirmatory_protocol"},
            "invalid subject",
        )
        digest(self.reviewed_fingerprint)
        if self.decision == HumanDecision.PENDING:
            check(
                not self.reviewer_name and not self.review_timestamp,
                "pending decision must be blank",
            )
            return
        check(bool(self.reviewer_name.strip()), "human reviewer name required")
        check(
            re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", self.review_timestamp)
            is not None,
            "human review timestamp must be UTC RFC 3339",
        )
        check(
            bool(self.checklist) and all(self.checklist.values()),
            "all review checks must be explicit",
        )

    def approves(self, current_fingerprint: str) -> bool:
        return (
            self.decision == HumanDecision.APPROVE
            and self.reviewed_fingerprint == current_fingerprint
            and bool(self.checklist)
            and all(self.checklist.values())
        )


@dataclass(frozen=True)
class Phase127Evidence:
    schema: str
    archguard_commit: str
    archguard_version: str
    runner_os: str
    host_architecture: str
    task_id: str
    framework_revision: str
    buggy_revision: str
    fixed_revision: str
    failure_signatures: tuple[str, ...]
    fixed_control: str
    evaluator: str
    profile_compilations: int
    profile_byte_identical: bool
    cleanup_complete: bool
    quarantine_complete: bool
    conclusion: str
    provenance: dict[str, str]
    fingerprint: str = ""

    def __post_init__(self) -> None:
        check(self.schema == IMPORTED_EVIDENCE_SCHEMA, "unsupported imported evidence schema")
        for revision in (
            self.archguard_commit,
            self.framework_revision,
            self.buggy_revision,
            self.fixed_revision,
        ):
            digest(revision)
        check(self.archguard_version == "0.12.6", "unexpected qualification version")
        check(self.runner_os == "Linux" and self.host_architecture == "x86_64", "wrong platform")
        check(len(self.failure_signatures) == 3, "exactly three buggy runs required")
        for signature in self.failure_signatures:
            digest(signature)
        check(len(set(self.failure_signatures)) == 1, "buggy failure signatures differ")
        check(
            self.fixed_control == "PASSED" and self.evaluator == "QUALIFIED",
            "evaluator not qualified",
        )
        check(
            self.profile_compilations == 3 and self.profile_byte_identical,
            "profile not deterministic",
        )
        check(self.cleanup_complete and self.quarantine_complete, "cleanup or quarantine failed")
        check(self.conclusion == "PASSED", "qualification conclusion did not pass")
        identity = fingerprint({k: v for k, v in asdict(self).items() if k != "fingerprint"})
        if self.fingerprint:
            check(self.fingerprint == identity, "evidence fingerprint mismatch")
        else:
            object.__setattr__(self, "fingerprint", identity)


MANDATORY_BLOCKERS = (
    "PHASE_12_7_EVIDENCE_MISSING",
    "INSUFFICIENT_QUALIFIED_TASKS",
    "INSUFFICIENT_PROJECT_DIVERSITY",
    "TASK_LIST_NOT_FROZEN",
    "LICENSES_UNVERIFIED",
    "EVALUATORS_UNQUALIFIED",
    "LINUX_X86_EVIDENCE_MISSING",
    "ARCHITECTURE_ANALYSIS_INCOMPLETE",
    "PROFILE_REVIEW_REQUIRED",
    "PROTOCOL_REVIEW_REQUIRED",
    "PROVIDER_NOT_CONFIGURED",
)


def readiness_report(facts: dict[str, Any]) -> dict[str, Any]:
    """Aggregate factual gates; callers cannot manually override readiness."""
    checks = {
        "PHASE_12_7_EVIDENCE_MISSING": bool(facts.get("phase_12_7_evidence")),
        "INSUFFICIENT_QUALIFIED_TASKS": int(facts.get("qualified_stable_tasks", 0)) >= 4,
        "INSUFFICIENT_PROJECT_DIVERSITY": int(facts.get("qualified_projects", 0)) >= 2,
        "TASK_LIST_NOT_FROZEN": bool(facts.get("task_list_frozen")),
        "LICENSES_UNVERIFIED": bool(facts.get("licenses_verified")),
        "EVALUATORS_UNQUALIFIED": bool(facts.get("evaluators_qualified")),
        "LINUX_X86_EVIDENCE_MISSING": bool(facts.get("linux_x86_evidence")),
        "ARCHITECTURE_ANALYSIS_INCOMPLETE": bool(facts.get("architecture_analysis_complete")),
        "PROFILE_REVIEW_REQUIRED": bool(facts.get("profiles_frozen")),
        "PROTOCOL_REVIEW_REQUIRED": bool(facts.get("protocol_frozen")),
        "PROVIDER_NOT_CONFIGURED": bool(facts.get("provider_decision_recorded")),
    }
    blockers = [code for code in MANDATORY_BLOCKERS if not checks[code]]
    result: dict[str, Any] = {
        "schema": READINESS_SCHEMA,
        "phase_13_ready": not blockers,
        "blocker_codes": blockers,
        "checks": checks,
    }
    result["fingerprint"] = fingerprint(result)
    return result
