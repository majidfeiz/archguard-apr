"""Immutable external-benchmark qualification and human-review contracts."""

from dataclasses import asdict, dataclass
from enum import StrEnum

from archguard.domain.orchestration import ArtifactReference, fingerprint, valid_id
from archguard.domain.repository import check, digest

READINESS_SCHEMA = "archguard.external-readiness/v1"
PROFILE_REVIEW_SCHEMA = "archguard.architecture-profile-review/v1"


class QualificationStage(StrEnum):
    METADATA = "STAGE_A_METADATA"
    ACQUISITION = "STAGE_B_ACQUISITION"
    LICENSE_AUDIT = "STAGE_C_LICENSE_AUDIT"
    REPRODUCTION = "STAGE_D_REPRODUCTION"
    ANALYSIS = "STAGE_E_ANALYSIS"
    PROFILE_DRAFTING = "STAGE_F_PROFILE_DRAFTING"
    HUMAN_REVIEW = "STAGE_G_HUMAN_REVIEW"
    EXTERNAL_PILOT = "STAGE_H_EXTERNAL_PILOT"
    PROTOCOL_FREEZE = "STAGE_I_PROTOCOL_FREEZE"
    PHASE13_READY = "STAGE_J_PHASE13_READY"


class GateStatus(StrEnum):
    NOT_STARTED = "not_started"
    BLOCKED = "blocked"
    REVIEW_REQUIRED = "review_required"
    PASSED = "passed"


class OverallReadiness(StrEnum):
    NOT_READY = "NOT_READY"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    PILOT_READY = "PILOT_READY"
    FINAL_EVALUATION_READY = "FINAL_EVALUATION_READY"


class Stability(StrEnum):
    STABLE = "STABLE"
    FLAKY = "FLAKY"
    ENVIRONMENT_SENSITIVE = "ENVIRONMENT_SENSITIVE"
    NOT_REPRODUCIBLE = "NOT_REPRODUCIBLE"
    UNKNOWN = "UNKNOWN"


class ProfileReviewState(StrEnum):
    DRAFT = "DRAFT"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    REVISED = "REVISED"
    APPROVED = "APPROVED"
    FROZEN = "FROZEN"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class AcquisitionRecord:
    artifact_id: str
    source_url: str
    immutable_revision: str
    observed_revision: str
    content_sha256: str
    acquisition_method: str
    byte_size: int
    classification: str
    complete: bool

    def __post_init__(self) -> None:
        valid_id(self.artifact_id)
        check(self.source_url.startswith("https://"), "invalid acquisition URL")
        check(self.immutable_revision == self.observed_revision, "acquired revision mismatch")
        digest(self.content_sha256)
        check(self.byte_size >= 0, "invalid acquisition size")
        check(
            self.classification in {"AGENT_VISIBLE", "EVALUATOR_ONLY", "GOLD_QUARANTINED"},
            "invalid acquisition classification",
        )


@dataclass(frozen=True)
class LicenseRecord:
    subject_id: str
    identifier: str | None
    source_url: str
    source_revision: str
    redistribution: str
    attribution: str
    modification: str
    replication_package: str
    unresolved_reason: str | None

    def __post_init__(self) -> None:
        valid_id(self.subject_id)
        check(self.source_url.startswith("https://"), "invalid license URL")
        check(
            self.redistribution in {"allowed", "restricted", "unresolved"},
            "invalid redistribution status",
        )
        check(
            (self.identifier is None) == (self.unresolved_reason is not None),
            "invalid license resolution",
        )


@dataclass(frozen=True)
class ReproductionRecord:
    task_id: str
    attempts: tuple[str, ...]
    stability: Stability
    expected_failure_reproduced: bool
    evaluator_verified: bool
    platform: str

    def __post_init__(self) -> None:
        valid_id(self.task_id)
        check(bool(self.attempts), "reproduction requires observations")
        check(
            self.stability != Stability.STABLE or len(set(self.attempts)) == 1,
            "stable classification contradicts observations",
        )


@dataclass(frozen=True)
class ProfileReviewDecision:
    schema: str
    profile_fingerprint: str
    reviewer_identity: str
    review_date: str
    decision: ProfileReviewState
    comments: str
    approved_rules: tuple[str, ...]
    rejected_rules: tuple[str, ...]
    requested_changes: tuple[str, ...]

    def __post_init__(self) -> None:
        check(self.schema == PROFILE_REVIEW_SCHEMA, "unsupported profile review schema")
        digest(self.profile_fingerprint)
        check(
            bool(self.reviewer_identity.strip()) and bool(self.review_date.strip()),
            "human reviewer identity and date required",
        )
        check(
            self.decision
            in {
                ProfileReviewState.APPROVED,
                ProfileReviewState.REJECTED,
                ProfileReviewState.REVISED,
            },
            "invalid human review decision",
        )
        check(
            not (set(self.approved_rules) & set(self.rejected_rules)),
            "rule cannot be approved and rejected",
        )


@dataclass(frozen=True)
class ReadinessGate:
    gate_id: str
    stage: QualificationStage
    required: bool
    status: GateStatus
    evidence: tuple[ArtifactReference, ...]
    blocker_reason: str | None
    reviewer_required: bool
    platform_requirement: str | None
    remediation: str

    def __post_init__(self) -> None:
        valid_id(self.gate_id)
        check(
            (self.status == GateStatus.PASSED) == bool(self.evidence),
            "passed gate requires evidence; unresolved gate must not claim evidence",
        )
        check(
            (self.status == GateStatus.PASSED) == (self.blocker_reason is None),
            "invalid gate blocker",
        )
        check(bool(self.remediation.strip()), "missing remediation")


@dataclass(frozen=True)
class ExternalReadiness:
    schema: str
    gates: tuple[ReadinessGate, ...]
    overall_status: OverallReadiness
    readiness_fingerprint: str = ""

    def __post_init__(self) -> None:
        check(self.schema == READINESS_SCHEMA, "unsupported readiness schema")
        check(
            tuple(sorted(self.gates, key=lambda item: item.gate_id)) == self.gates,
            "readiness gates must be sorted",
        )
        check(
            len({item.gate_id for item in self.gates}) == len(self.gates),
            "duplicate readiness gate",
        )
        mandatory = tuple(item for item in self.gates if item.required)
        all_passed = bool(mandatory) and all(item.status == GateStatus.PASSED for item in mandatory)
        human_pending = any(
            item.reviewer_required and item.status != GateStatus.PASSED for item in mandatory
        )
        expected = (
            OverallReadiness.FINAL_EVALUATION_READY
            if all_passed
            else OverallReadiness.REVIEW_REQUIRED
            if human_pending
            else OverallReadiness.NOT_READY
        )
        check(self.overall_status == expected, "readiness status cannot be forged")
        identity = fingerprint(
            {key: value for key, value in asdict(self).items() if key != "readiness_fingerprint"}
        )
        if self.readiness_fingerprint:
            check(self.readiness_fingerprint == identity, "readiness fingerprint mismatch")
        else:
            object.__setattr__(self, "readiness_fingerprint", identity)
