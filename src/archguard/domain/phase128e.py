"""Phase 12.8E license records and outcome-blind preparation-pool selection."""

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from archguard.domain.orchestration import fingerprint, valid_id
from archguard.domain.readiness import git_sha1_commit, sha256_digest
from archguard.domain.repository import check

LICENSE_SCHEMA = "archguard.license-registry/v1"
CANDIDATE_SCHEMA = "archguard.candidate-pool/v1"
POLICY_SCHEMA = "archguard.candidate-selection-policy/v1"
FORBIDDEN_OUTCOME_KEYS = frozenset(
    {
        "gold_patch",
        "reference_patch",
        "patch",
        "repair_outcome",
        "repair_success",
        "benchmark_score",
        "fixed_code",
    }
)


class AuditStatus(StrEnum):
    VERIFIED = "VERIFIED"
    UNRESOLVED = "UNRESOLVED"
    INELIGIBLE = "INELIGIBLE"


@dataclass(frozen=True)
class LicenseRecord:
    subject_id: str
    subject_kind: str
    official_source_url: str
    immutable_locator: str
    license_file_path: str | None
    license_sha256: str | None
    spdx_identifier: str | None
    redistribution_status: AuditStatus
    benchmark_use_status: AuditStatus
    source_execution_status: AuditStatus
    evidence_timestamp: str
    evidence_type: str
    audit_status: AuditStatus
    reason: str
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        valid_id(self.subject_id)
        check(self.subject_kind in {"framework", "dataset", "project"}, "invalid subject kind")
        check(self.official_source_url.startswith("https://"), "official HTTPS source required")
        check(bool(self.immutable_locator), "immutable evidence locator required")
        check(bool(self.reason) and bool(self.evidence_type), "incomplete audit explanation")
        if self.license_sha256 is not None:
            sha256_digest(self.license_sha256)
            check(bool(self.license_file_path), "license hash requires license path")
        if self.audit_status is AuditStatus.VERIFIED:
            check(
                self.license_sha256 is not None and self.spdx_identifier is not None,
                "VERIFIED requires official hashed license and defensible SPDX",
            )
        else:
            check(self.spdx_identifier is None, "unverified license cannot infer SPDX")


@dataclass(frozen=True)
class CandidateRecord:
    task_id: str
    source_index: str
    source_revision: str
    project: str
    official_repository: str
    language: str
    buggy_revision: str
    fixed_revision: str
    evaluator_locator: str
    python_version: str
    checkout_archive_bytes: int
    cpu_limit: int
    memory_limit_bytes: int
    timeout_minutes: int
    repetitions: int
    requires_secrets: bool
    evaluator_network_required: bool
    unsupported_gitlink: bool
    lfs_required: bool
    license_record: str
    eligible: bool
    ineligible_reason: str | None

    def __post_init__(self) -> None:
        valid_id(self.task_id)
        git_sha1_commit(self.source_revision)
        git_sha1_commit(self.buggy_revision)
        git_sha1_commit(self.fixed_revision)
        check(self.language == "Python", "only Python candidates are supported")
        check(
            self.official_repository.startswith("https://github.com/"),
            "official repository required",
        )
        check(0 < self.checkout_archive_bytes <= 2 * 1024**3, "unbounded checkout")
        check(
            self.cpu_limit <= 2 and self.memory_limit_bytes <= 2 * 1024**3,
            "resource ceiling exceeded",
        )
        check(
            self.timeout_minutes <= 20 and self.repetitions <= 3, "qualification ceiling exceeded"
        )
        check(self.eligible == (self.ineligible_reason is None), "eligibility contradiction")
        if self.eligible:
            check(not self.requires_secrets, "eligible candidate requires secrets")
            check(not self.evaluator_network_required, "eligible evaluator requires network")
            check(
                not self.unsupported_gitlink and not self.lfs_required,
                "unsupported repository dependency",
            )


def reject_outcome_fields(value: Any) -> None:
    """Fail closed if candidate input includes repair-result or hidden-answer material."""
    if isinstance(value, dict):
        for key, item in value.items():
            check(str(key).lower() not in FORBIDDEN_OUTCOME_KEYS, "outcome/gold field prohibited")
            reject_outcome_fields(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            reject_outcome_fields(item)


def select_preparation_pool(
    candidates: tuple[CandidateRecord, ...], *, minimum: int = 8, maximum: int = 12, cap: int = 4
) -> tuple[CandidateRecord, ...]:
    """Select deterministically by project-stratified round robin without outcome data."""
    check(8 <= minimum <= maximum <= 12 and 1 <= cap <= 4, "invalid selection bounds")
    reject_outcome_fields([asdict(candidate) for candidate in candidates])
    eligible = sorted((item for item in candidates if item.eligible), key=lambda item: item.task_id)
    projects = sorted({item.project for item in eligible})
    grouped = {
        project: [item for item in eligible if item.project == project] for project in projects
    }
    selected: list[CandidateRecord] = []
    for index in range(cap):
        for project in projects:
            if index < len(grouped[project]) and len(selected) < maximum:
                selected.append(grouped[project][index])
    check(len(selected) >= minimum, "insufficient eligible preparation pool")
    return tuple(selected)


def fingerprinted(schema: str, body: dict[str, Any]) -> dict[str, Any]:
    check(
        schema in {LICENSE_SCHEMA, CANDIDATE_SCHEMA, POLICY_SCHEMA},
        "unsupported Phase 12.8E schema",
    )
    reject_outcome_fields(body)
    result = {"schema": schema, **body}
    result["fingerprint"] = fingerprint(result)
    return result
