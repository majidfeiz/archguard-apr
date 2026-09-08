"""Immutable, source-free candidate patch and architecture-delta contracts."""

import hashlib
from dataclasses import asdict, dataclass, is_dataclass
from enum import StrEnum
from typing import Any

from archguard.domain.architecture_report import (
    ArchitectureReport,
    ArchitectureSummary,
    ArchitectureViolation,
    CycleEvidence,
    DependencyEvidence,
)
from archguard.domain.canonical import canonical_json
from archguard.domain.enums import Severity
from archguard.domain.repository import check, digest, safe_path

CANDIDATE_PATCH_SCHEMA_VERSION = "1"
ARCHITECTURE_DELTA_SCHEMA_VERSION = "1"
PATCH_VALIDATION_SCHEMA_VERSION = "1"
MAX_PATCH_BYTES = 4 * 1024 * 1024
MAX_PATCH_OPERATIONS = 256
MAX_PATCH_PATH_BYTES = 512


class PatchOperationKind(StrEnum):
    ADD = "add"
    MODIFY = "modify"
    DELETE = "delete"


class PatchDiagnosticCode(StrEnum):
    EMPTY = "empty_patch"
    TOO_LARGE = "patch_too_large"
    NUL = "nul_byte"
    MALFORMED = "malformed_diff"
    UNSAFE_PATH = "unsafe_path"
    GIT_PATH = "git_path"
    CONTROL_PATH = "control_character_path"
    PATH_TOO_LONG = "path_too_long"
    BINARY = "binary_patch"
    RENAME_COPY = "rename_copy_unsupported"
    UNSAFE_MODE = "unsafe_file_mode"
    TOO_MANY_OPERATIONS = "too_many_operations"
    DUPLICATE_PATH = "duplicate_path_operation"
    OUTSIDE_ALLOWED_ROOT = "outside_allowed_root"
    PROTECTED_PATH = "protected_path"
    APPLICATION_FAILED = "patch_does_not_apply"


PATCH_MESSAGES = {
    PatchDiagnosticCode.EMPTY: "Patch input is empty.",
    PatchDiagnosticCode.TOO_LARGE: "Patch exceeds the byte limit.",
    PatchDiagnosticCode.NUL: "Patch contains a NUL byte.",
    PatchDiagnosticCode.MALFORMED: "Patch is not a supported unified diff.",
    PatchDiagnosticCode.UNSAFE_PATH: "Patch contains an unsafe path.",
    PatchDiagnosticCode.GIT_PATH: "Patch targets Git metadata.",
    PatchDiagnosticCode.CONTROL_PATH: "Patch path contains unsupported characters.",
    PatchDiagnosticCode.PATH_TOO_LONG: "Patch path exceeds the byte limit.",
    PatchDiagnosticCode.BINARY: "Binary patches are unsupported.",
    PatchDiagnosticCode.RENAME_COPY: "Rename and copy patches are unsupported.",
    PatchDiagnosticCode.UNSAFE_MODE: "Symlink and gitlink mode changes are unsupported.",
    PatchDiagnosticCode.TOO_MANY_OPERATIONS: "Patch exceeds the operation limit.",
    PatchDiagnosticCode.DUPLICATE_PATH: "Patch contains duplicate target operations.",
    PatchDiagnosticCode.OUTSIDE_ALLOWED_ROOT: "Patch target is outside allowed roots.",
    PatchDiagnosticCode.PROTECTED_PATH: "Patch targets a protected path.",
    PatchDiagnosticCode.APPLICATION_FAILED: "Patch does not apply to the exact baseline.",
}


@dataclass(frozen=True, order=True)
class PatchDiagnostic:
    code: PatchDiagnosticCode
    message: str

    def __post_init__(self) -> None:
        check(self.message == PATCH_MESSAGES[self.code], "invalid patch diagnostic message")


@dataclass(frozen=True, order=True)
class PatchOperation:
    path: str
    kind: PatchOperationKind

    def __post_init__(self) -> None:
        safe_path(self.path)
        check(len(self.path.encode("utf-8")) <= MAX_PATCH_PATH_BYTES, "patch path too long")


@dataclass(frozen=True)
class CandidatePatch:
    candidate_patch_schema_version: str
    patch_fingerprint: str
    byte_size: int
    operations: tuple[PatchOperation, ...]
    binary_patch_present: bool
    diagnostics: tuple[PatchDiagnostic, ...]
    acceptable: bool

    def __post_init__(self) -> None:
        check(
            self.candidate_patch_schema_version == CANDIDATE_PATCH_SCHEMA_VERSION,
            "unsupported patch schema",
        )
        digest(self.patch_fingerprint)
        check(self.byte_size >= 0, "invalid patch byte size")
        object.__setattr__(self, "operations", tuple(self.operations))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        check(self.operations == tuple(sorted(self.operations)), "unordered patch operations")
        check(
            self.diagnostics == tuple(sorted(set(self.diagnostics))), "unordered patch diagnostics"
        )
        check(
            self.acceptable == (bool(self.operations) and not self.diagnostics),
            "invalid acceptance status",
        )

    @property
    def changed_paths(self) -> tuple[str, ...]:
        return tuple(operation.path for operation in self.operations)

    def paths(self, kind: PatchOperationKind) -> tuple[str, ...]:
        return tuple(operation.path for operation in self.operations if operation.kind == kind)


type SemanticKey = tuple[str, ...]


def semantic_key(violation: ArchitectureViolation) -> SemanticKey:
    evidence = violation.evidence
    if isinstance(evidence, CycleEvidence):
        return (violation.rule_id, violation.category, *evidence.module_ids)
    assert isinstance(evidence, DependencyEvidence)
    return (
        violation.rule_id,
        violation.category,
        evidence.source_module_id,
        evidence.target_module_id,
    )


@dataclass(frozen=True)
class PersistingViolation:
    semantic_key: SemanticKey
    baseline: ArchitectureViolation
    candidate: ArchitectureViolation


@dataclass(frozen=True)
class ArchitectureDelta:
    architecture_delta_schema_version: str
    baseline_commit: str
    patch_fingerprint: str
    profile_fingerprint: str
    baseline_snapshot_fingerprint: str
    candidate_snapshot_fingerprint: str
    baseline_graph_fingerprint: str
    candidate_graph_fingerprint: str
    baseline_report_fingerprint: str
    candidate_report_fingerprint: str
    introduced: tuple[ArchitectureViolation, ...]
    resolved: tuple[ArchitectureViolation, ...]
    persisting: tuple[PersistingViolation, ...]
    baseline_summary: ArchitectureSummary
    candidate_summary: ArchitectureSummary
    comparison_complete: bool
    incompleteness_reasons: tuple[str, ...]
    architecture_passed: bool
    delta_fingerprint: str

    def __post_init__(self) -> None:
        check(
            self.architecture_delta_schema_version == ARCHITECTURE_DELTA_SCHEMA_VERSION,
            "unsupported delta schema",
        )
        for value in (
            self.patch_fingerprint,
            self.profile_fingerprint,
            self.baseline_snapshot_fingerprint,
            self.candidate_snapshot_fingerprint,
            self.baseline_graph_fingerprint,
            self.candidate_graph_fingerprint,
            self.baseline_report_fingerprint,
            self.candidate_report_fingerprint,
        ):
            digest(value)
        check(
            len(self.baseline_commit) == 40
            and all(c in "0123456789abcdef" for c in self.baseline_commit),
            "invalid baseline commit",
        )
        for field in ("introduced", "resolved", "persisting", "incompleteness_reasons"):
            object.__setattr__(self, field, tuple(getattr(self, field)))
        check(
            self.incompleteness_reasons == tuple(sorted(set(self.incompleteness_reasons))),
            "unordered incompleteness reasons",
        )
        check(
            self.comparison_complete == (not self.incompleteness_reasons),
            "invalid comparison completeness",
        )
        check(
            self.architecture_passed
            == (
                self.comparison_complete
                and not any(v.severity == Severity.ERROR for v in self.introduced)
            ),
            "invalid architecture gate",
        )
        check(self.delta_fingerprint == delta_identity(self), "delta fingerprint mismatch")


def delta_identity(delta: ArchitectureDelta) -> str:
    data = asdict(delta)
    data.pop("delta_fingerprint", None)
    return hashlib.sha256(canonical_json(data)).hexdigest()


def _fingerprint_values(values: dict[str, object]) -> str:
    def plain(value: object) -> object:
        if is_dataclass(value) and not isinstance(value, type):
            return {key: plain(item) for key, item in asdict(value).items()}
        if isinstance(value, dict):
            return {str(key): plain(item) for key, item in value.items()}
        if isinstance(value, (tuple, list)):
            return [plain(item) for item in value]
        return value

    return hashlib.sha256(canonical_json(plain(values))).hexdigest()


def compare_reports(
    baseline_commit: str,
    patch_fingerprint: str,
    baseline_snapshot: str,
    candidate_snapshot: str,
    baseline_graph: str,
    candidate_graph: str,
    baseline: ArchitectureReport,
    candidate: ArchitectureReport,
) -> ArchitectureDelta:
    check(baseline.profile_fingerprint == candidate.profile_fingerprint, "profile mismatch")
    before = _unique(baseline.violations)
    after = _unique(candidate.violations)
    introduced = tuple(after[k] for k in sorted(after.keys() - before.keys()))
    resolved = tuple(before[k] for k in sorted(before.keys() - after.keys()))
    persisting = tuple(
        PersistingViolation(k, before[k], after[k]) for k in sorted(before.keys() & after.keys())
    )
    reasons = tuple(
        sorted(
            {
                reason
                for partial, reason in (
                    (baseline.summary.partial, "baseline_incomplete"),
                    (candidate.summary.partial, "candidate_incomplete"),
                )
                if partial
            }
        )
    )
    values: dict[str, Any] = dict(
        architecture_delta_schema_version=ARCHITECTURE_DELTA_SCHEMA_VERSION,
        baseline_commit=baseline_commit,
        patch_fingerprint=patch_fingerprint,
        profile_fingerprint=baseline.profile_fingerprint,
        baseline_snapshot_fingerprint=baseline_snapshot,
        candidate_snapshot_fingerprint=candidate_snapshot,
        baseline_graph_fingerprint=baseline_graph,
        candidate_graph_fingerprint=candidate_graph,
        baseline_report_fingerprint=baseline.report_fingerprint,
        candidate_report_fingerprint=candidate.report_fingerprint,
        introduced=introduced,
        resolved=resolved,
        persisting=persisting,
        baseline_summary=baseline.summary,
        candidate_summary=candidate.summary,
        comparison_complete=not reasons,
        incompleteness_reasons=reasons,
        architecture_passed=not reasons
        and not any(v.severity == Severity.ERROR for v in introduced),
    )
    return ArchitectureDelta(**values, delta_fingerprint=_fingerprint_values(values))


def _unique(
    violations: tuple[ArchitectureViolation, ...],
) -> dict[SemanticKey, ArchitectureViolation]:
    result: dict[SemanticKey, ArchitectureViolation] = {}
    for violation in violations:
        key = semantic_key(violation)
        check(key not in result, "duplicate semantic violation key")
        result[key] = violation
    return result


class ValidationStatus(StrEnum):
    REJECTED = "rejected"
    APPLICATION_FAILED = "application_failed"
    ANALYSIS_FAILED = "analysis_failed"
    COMPLETED = "completed"


@dataclass(frozen=True)
class RepositoryStateProof:
    head_commit: str
    branch: str | None
    index_tree: str
    tracked_status_sha256: str
    untracked_status_sha256: str

    def __post_init__(self) -> None:
        for value in (self.index_tree, self.tracked_status_sha256, self.untracked_status_sha256):
            digest(value)


@dataclass(frozen=True)
class PatchValidationResult:
    patch_validation_schema_version: str
    status: ValidationStatus
    baseline_commit: str
    patch: CandidatePatch
    patch_applied: bool
    comparison_complete: bool
    architecture_passed: bool
    validation_completed: bool
    diagnostic_codes: tuple[str, ...]
    repository_state_before: RepositoryStateProof
    repository_state_after: RepositoryStateProof
    delta: ArchitectureDelta | None
    result_fingerprint: str

    def __post_init__(self) -> None:
        check(
            self.patch_validation_schema_version == PATCH_VALIDATION_SCHEMA_VERSION,
            "unsupported validation schema",
        )
        object.__setattr__(self, "diagnostic_codes", tuple(self.diagnostic_codes))
        check(
            self.diagnostic_codes == tuple(sorted(set(self.diagnostic_codes))),
            "unordered validation diagnostics",
        )
        check(
            self.repository_state_before == self.repository_state_after,
            "original repository state changed",
        )
        check(
            self.comparison_complete == (self.delta is not None and self.delta.comparison_complete),
            "invalid comparison status",
        )
        check(
            self.architecture_passed == (self.delta is not None and self.delta.architecture_passed),
            "invalid gate status",
        )
        check(
            self.validation_completed == (self.status == ValidationStatus.COMPLETED),
            "invalid completion status",
        )
        check(self.result_fingerprint == result_identity(self), "result fingerprint mismatch")

    @property
    def exit_code(self) -> int:
        if self.status == ValidationStatus.REJECTED:
            return 3
        if self.status == ValidationStatus.APPLICATION_FAILED:
            return 5
        if not self.comparison_complete:
            return 4
        return 0 if self.architecture_passed else 1


def result_identity(result: PatchValidationResult) -> str:
    data = asdict(result)
    data.pop("result_fingerprint", None)
    return hashlib.sha256(canonical_json(data)).hexdigest()


def create_validation_result(
    status: ValidationStatus,
    baseline_commit: str,
    patch: CandidatePatch,
    before: RepositoryStateProof,
    after: RepositoryStateProof,
    delta: ArchitectureDelta | None = None,
    diagnostic_codes: tuple[str, ...] = (),
    patch_applied: bool = False,
) -> PatchValidationResult:
    values: dict[str, Any] = dict(
        patch_validation_schema_version=PATCH_VALIDATION_SCHEMA_VERSION,
        status=status,
        baseline_commit=baseline_commit,
        patch=patch,
        patch_applied=patch_applied,
        comparison_complete=delta is not None and delta.comparison_complete,
        architecture_passed=delta is not None and delta.architecture_passed,
        validation_completed=status == ValidationStatus.COMPLETED,
        diagnostic_codes=tuple(sorted(set(diagnostic_codes))),
        repository_state_before=before,
        repository_state_after=after,
        delta=delta,
    )
    return PatchValidationResult(**values, result_fingerprint=_fingerprint_values(values))
