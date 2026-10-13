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
BOUND_DECISION_SCHEMA = "archguard.human-decision/v2"
APPROVAL_DECISION_SCHEMA = "archguard.human-decision/v3"
PROTOCOL_APPROVAL_DECISION_SCHEMA = "archguard.human-decision/v4"
PROTOCOL_SCHEMA = "archguard.confirmatory-protocol/v1"
READINESS_SCHEMA = "archguard.phase-13-readiness/v1"


def git_sha1_commit(value: str) -> str:
    """Validate a full lowercase SHA-1 Git object ID used as a commit revision."""
    check(re.fullmatch(r"[0-9a-f]{40}", value) is not None, "invalid Git SHA-1 commit ID")
    return value


def sha256_digest(value: str) -> str:
    """Validate an unprefixed lowercase SHA-256 digest."""
    check(re.fullmatch(r"[0-9a-f]{64}", value) is not None, "invalid SHA-256 digest")
    return value


def docker_sha256_digest(value: str) -> str:
    """Validate a Docker image ID with an explicit SHA-256 algorithm prefix."""
    check(
        re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None,
        "invalid Docker SHA-256 digest",
    )
    return value


class HumanDecision(StrEnum):
    PENDING = "PENDING"
    APPROVE = "APPROVE"
    REQUEST_CHANGES = "REQUEST_CHANGES"
    REJECT = "REJECT"
    AMEND = "AMEND"


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
    evidence_binding: dict[str, str] | None = None
    approval_binding: dict[str, str] | None = None
    previous_decision_sha256: str | None = None

    def __post_init__(self) -> None:
        check(
            self.schema
            in {
                DECISION_SCHEMA,
                BOUND_DECISION_SCHEMA,
                APPROVAL_DECISION_SCHEMA,
                PROTOCOL_APPROVAL_DECISION_SCHEMA,
            },
            "unsupported human decision schema",
        )
        check(
            self.subject_kind
            in {
                "architecture_profile",
                "confirmatory_protocol",
                "exploratory_feasibility_protocol",
            },
            "invalid subject",
        )
        digest(self.reviewed_fingerprint)
        if self.schema == BOUND_DECISION_SCHEMA:
            binding = self.evidence_binding or {}
            check(
                set(binding)
                == {
                    "graph_fingerprint",
                    "canonical_graph_fingerprint",
                    "acquisition_fingerprint",
                    "buggy_revision",
                    "task_id",
                },
                "invalid evidence binding",
            )
            for key in (
                "graph_fingerprint",
                "canonical_graph_fingerprint",
                "acquisition_fingerprint",
            ):
                sha256_digest(binding[key])
            git_sha1_commit(binding["buggy_revision"])
            check(binding["task_id"] == "PySnooper-2", "wrong bound task")
            check(self.approval_binding is None, "AMEND decision cannot carry approval binding")
            check(self.previous_decision_sha256 is None, "AMEND decision cannot carry history")
        elif self.schema == PROTOCOL_APPROVAL_DECISION_SCHEMA:
            binding = self.approval_binding or {}
            check(
                set(binding) == {"population_fingerprint", "protocol_definition_fingerprint"},
                "invalid protocol approval binding",
            )
            sha256_digest(binding["population_fingerprint"])
            sha256_digest(binding["protocol_definition_fingerprint"])
            sha256_digest(self.previous_decision_sha256 or "")
            check(self.decision == HumanDecision.APPROVE, "v4 is reserved for approval")
            check(self.evidence_binding is None, "approval cannot use AMEND binding")
        elif self.schema == APPROVAL_DECISION_SCHEMA:
            binding = self.approval_binding or {}
            check(
                set(binding)
                == {
                    "canonical_archive_sha256",
                    "github_run_id",
                    "task_id",
                    "buggy_revision",
                    "manifest_fingerprint",
                    "profile_fingerprint",
                    "graph_fingerprint",
                    "canonical_graph_fingerprint",
                    "constraint_evaluation_fingerprint",
                    "imported_evidence_fingerprint",
                },
                "invalid approval binding",
            )
            for key in (
                "canonical_archive_sha256",
                "manifest_fingerprint",
                "profile_fingerprint",
                "graph_fingerprint",
                "canonical_graph_fingerprint",
                "constraint_evaluation_fingerprint",
                "imported_evidence_fingerprint",
            ):
                sha256_digest(binding[key])
            git_sha1_commit(binding["buggy_revision"])
            check(binding["task_id"] == "PySnooper-2", "wrong bound task")
            check(binding["github_run_id"].isdigit(), "invalid GitHub run ID")
            check(self.evidence_binding is None, "approval cannot use AMEND binding")
            sha256_digest(self.previous_decision_sha256 or "")
            check(self.decision == HumanDecision.APPROVE, "v3 is reserved for approval")
            check(
                self.reviewed_fingerprint == binding["profile_fingerprint"],
                "approval reviewed fingerprint mismatch",
            )
        else:
            check(self.evidence_binding is None, "v1 decision cannot carry evidence binding")
            check(self.approval_binding is None, "v1 decision cannot carry approval binding")
            check(self.previous_decision_sha256 is None, "v1 decision cannot carry history")
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
    license_file_sha256: str
    profile_artifact_sha256: str
    evaluator_image_digest: str
    evaluator_image_architecture: str
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
            git_sha1_commit(revision)
        sha256_digest(self.license_file_sha256)
        sha256_digest(self.profile_artifact_sha256)
        docker_sha256_digest(self.evaluator_image_digest)
        check(self.evaluator_image_architecture == "amd64", "wrong evaluator architecture")
        check(self.archguard_version == "0.12.6", "unexpected qualification version")
        check(self.runner_os == "Linux" and self.host_architecture == "x86_64", "wrong platform")
        check(len(self.failure_signatures) == 3, "exactly three buggy runs required")
        for signature in self.failure_signatures:
            sha256_digest(signature)
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
    "INSUFFICIENT_CANDIDATE_POOL",
    "PILOT_SELECTION_NOT_READY",
    "GRAPH_EVIDENCE_EXTERNAL_EXECUTION_REQUIRED",
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
    if facts.get("study_designation") == "Exploratory Multi-Project Feasibility Protocol":
        scientific_checks = {
            "PHASE_12_7_EVIDENCE_MISSING": bool(facts.get("phase_12_7_evidence")),
            "INSUFFICIENT_QUALIFIED_TASKS": int(facts.get("qualified_stable_tasks", 0)) == 3,
            "INSUFFICIENT_PROJECT_DIVERSITY": int(facts.get("qualified_projects", 0)) == 2,
            "INSUFFICIENT_CANDIDATE_POOL": int(facts.get("candidate_pool_count", 0)) >= 8,
            "PILOT_SELECTION_NOT_READY": int(facts.get("selected_pilot_tasks", 0)) == 3,
            "GRAPH_EVIDENCE_EXTERNAL_EXECUTION_REQUIRED": bool(
                facts.get("graph_evidence_validated")
            ),
            "TASK_LIST_NOT_FROZEN": bool(facts.get("task_list_frozen")),
            "LICENSES_UNVERIFIED": bool(facts.get("frozen_population_licenses_verified")),
            "EVALUATORS_UNQUALIFIED": bool(facts.get("evaluators_qualified")),
            "LINUX_X86_EVIDENCE_MISSING": bool(facts.get("linux_x86_evidence")),
            "ARCHITECTURE_ANALYSIS_INCOMPLETE": bool(facts.get("architecture_analysis_complete")),
            "PROFILE_REVIEW_REQUIRED": bool(facts.get("profiles_frozen")),
            "PROTOCOL_REVIEW_REQUIRED": bool(facts.get("protocol_frozen")),
        }
        scientific_blockers = [code for code, passed in scientific_checks.items() if not passed]
        operational_checks = {
            "PROVIDER_NOT_CONFIGURED": bool(facts.get("provider_decision_recorded")),
            "PHASE_13_PROTOCOL_NOT_AMENDED": facts.get("phase_13_protocol_fingerprint")
            == "eae1920ce71c025d2d94096798daf8b14df098249743631efe9a0aa7a541fbe8"
            and facts.get("phase_13_protocol_amendment_fingerprint")
            == "c2e40ab75500db061269f51f781bca06125e4f2a5d80fed3a90e5300fccbab38",
        }
        operational_blockers = [code for code, passed in operational_checks.items() if not passed]
        phase_12_complete = not scientific_blockers
        scientifically_ready = phase_12_complete
        operationally_ready = scientifically_ready and not operational_blockers
        exploratory_result = {
            "schema": "archguard.phase-13-readiness/v2",
            "phase_12_complete": phase_12_complete,
            "phase_13_scientifically_ready": scientifically_ready,
            "phase_13_operationally_ready": operationally_ready,
            "phase_13_ready": operationally_ready,
            "blocker_codes": scientific_blockers + operational_blockers,
            "scientific_checks": scientific_checks,
            "operational_checks": operational_checks,
        }
        exploratory_result["fingerprint"] = fingerprint(exploratory_result)
        return exploratory_result
    checks = {
        "PHASE_12_7_EVIDENCE_MISSING": bool(facts.get("phase_12_7_evidence")),
        "INSUFFICIENT_QUALIFIED_TASKS": int(facts.get("qualified_stable_tasks", 0)) >= 4,
        "INSUFFICIENT_PROJECT_DIVERSITY": int(facts.get("qualified_projects", 0)) >= 2,
        "INSUFFICIENT_CANDIDATE_POOL": int(facts.get("candidate_pool_count", 0)) >= 8,
        "PILOT_SELECTION_NOT_READY": 4 <= int(facts.get("selected_pilot_tasks", 0)) <= 6,
        "GRAPH_EVIDENCE_EXTERNAL_EXECUTION_REQUIRED": bool(facts.get("graph_evidence_validated")),
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
