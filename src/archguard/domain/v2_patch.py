"""Provider-neutral V2 repair-response and source-free diagnostic contracts."""

import hashlib
from dataclasses import asdict, dataclass
from enum import StrEnum

from archguard.domain.canonical import canonical_json
from archguard.domain.repository import check, digest, safe_path

REPAIR_RESPONSE_SCHEMA = "archguard.repair-response/v2.1"
PATCH_DIAGNOSTIC_SCHEMA = "archguard.patch-diagnostic/v2.1"
MAX_RESPONSE_BYTES = 4 * 1024 * 1024 + 16 * 1024
MAX_TASK_ID_BYTES = 256
MAX_CANDIDATE_ID_BYTES = 256
MAX_RATIONALE_BYTES = 2048
MAX_DECLARED_PATHS = 256
MAX_PATCH_FILES = 256
MAX_PATCH_HUNKS = 1024
MAX_PATCH_LINES = 100_000


class PatchStage(StrEnum):
    RESPONSE_PARSING = "response_parsing"
    PATCH_EXTRACTION = "patch_extraction"
    DIFF_VALIDATION = "diff_validation"
    POLICY_VALIDATION = "policy_validation"
    PATCH_APPLICATION = "patch_application"
    ARCHITECTURE_VALIDATION = "architecture_validation"
    EVIDENCE_VALIDATION = "evidence_validation"


class V2PatchDiagnosticCode(StrEnum):
    NO_PATCH_FOUND = "NO_PATCH_FOUND"
    MULTIPLE_PATCHES_FOUND = "MULTIPLE_PATCHES_FOUND"
    AMBIGUOUS_RESPONSE = "AMBIGUOUS_RESPONSE"
    RESPONSE_SCHEMA_INVALID = "RESPONSE_SCHEMA_INVALID"
    PATCH_TOO_LARGE = "PATCH_TOO_LARGE"
    MALFORMED_DIFF_HEADER = "MALFORMED_DIFF_HEADER"
    TRUNCATED_DIFF = "TRUNCATED_DIFF"
    UNSUPPORTED_PATCH_OPERATION = "UNSUPPORTED_PATCH_OPERATION"
    UNSAFE_PATH = "UNSAFE_PATH"
    DECLARED_PATH_MISMATCH = "DECLARED_PATH_MISMATCH"
    PATCH_CONTEXT_MISMATCH = "PATCH_CONTEXT_MISMATCH"
    PATCH_APPLICATION_FAILED = "PATCH_APPLICATION_FAILED"
    NO_EFFECTIVE_CHANGE = "NO_EFFECTIVE_CHANGE"
    POLICY_REJECTED = "POLICY_REJECTED"
    ARCHITECTURE_REJECTED = "ARCHITECTURE_REJECTED"
    EVIDENCE_CONTRADICTION = "EVIDENCE_CONTRADICTION"


@dataclass(frozen=True, order=True)
class V2PatchDiagnostic:
    stage: PatchStage
    code: V2PatchDiagnosticCode
    fingerprint: str

    @classmethod
    def create(cls, stage: PatchStage, code: V2PatchDiagnosticCode) -> "V2PatchDiagnostic":
        fingerprint = hashlib.sha256(
            canonical_json(
                {"code": code.value, "schema": PATCH_DIAGNOSTIC_SCHEMA, "stage": stage.value}
            )
        ).hexdigest()
        return cls(stage, code, fingerprint)

    def __post_init__(self) -> None:
        digest(self.fingerprint)
        expected = hashlib.sha256(
            canonical_json(
                {
                    "code": self.code.value,
                    "schema": PATCH_DIAGNOSTIC_SCHEMA,
                    "stage": self.stage.value,
                }
            )
        ).hexdigest()
        check(self.fingerprint == expected, "diagnostic fingerprint mismatch")


@dataclass(frozen=True)
class RepairResponse:
    schema_version: str
    task_id: str
    candidate_id: str
    unified_diff: str
    declared_changed_paths: tuple[str, ...]
    rationale_summary: str | None = None

    def __post_init__(self) -> None:
        check(self.schema_version == REPAIR_RESPONSE_SCHEMA, "unsupported response schema")
        _bounded_text(self.task_id, MAX_TASK_ID_BYTES, "task identifier")
        _bounded_text(self.candidate_id, MAX_CANDIDATE_ID_BYTES, "candidate identifier")
        check(bool(self.unified_diff), "empty unified diff")
        check(len(self.unified_diff.encode("utf-8")) <= MAX_RESPONSE_BYTES, "patch too large")
        object.__setattr__(self, "declared_changed_paths", tuple(self.declared_changed_paths))
        check(
            0 < len(self.declared_changed_paths) <= MAX_DECLARED_PATHS,
            "invalid declared path count",
        )
        check(
            self.declared_changed_paths == tuple(sorted(set(self.declared_changed_paths))),
            "declared paths must be unique and sorted",
        )
        for path in self.declared_changed_paths:
            safe_path(path)
        if self.rationale_summary is not None:
            _bounded_text(self.rationale_summary, MAX_RATIONALE_BYTES, "rationale summary")


@dataclass(frozen=True)
class ExtractedPatch:
    schema_version: str
    input_format: str
    raw_input_sha256: str
    normalized_patch_sha256: str | None
    normalized_patch: bytes | None
    declared_changed_paths: tuple[str, ...]
    diagnostics: tuple[V2PatchDiagnostic, ...]

    def __post_init__(self) -> None:
        check(self.schema_version == PATCH_DIAGNOSTIC_SCHEMA, "unsupported extraction schema")
        check(
            self.input_format in {"raw_diff", "markdown_fence", "structured", "rejected"},
            "bad format",
        )
        digest(self.raw_input_sha256)
        object.__setattr__(self, "declared_changed_paths", tuple(self.declared_changed_paths))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        check(self.diagnostics == tuple(sorted(set(self.diagnostics))), "unordered diagnostics")
        if self.normalized_patch is None:
            check(self.normalized_patch_sha256 is None, "patch fingerprint without patch")
        else:
            check(not self.diagnostics, "rejected extraction retained patch")
            check(self.normalized_patch_sha256 is not None, "missing patch fingerprint")
            check(
                hashlib.sha256(self.normalized_patch).hexdigest() == self.normalized_patch_sha256,
                "normalized patch fingerprint mismatch",
            )

    def source_free_evidence(self) -> dict[str, object]:
        value = asdict(self)
        value.pop("normalized_patch")
        return value


def _bounded_text(value: str, maximum: int, label: str) -> None:
    check(bool(value) and value.strip() == value, f"invalid {label}")
    check(len(value.encode("utf-8")) <= maximum, f"{label} too large")
    check(all(ord(character) >= 32 for character in value), f"invalid {label}")
