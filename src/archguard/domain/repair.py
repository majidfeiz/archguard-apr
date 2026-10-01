"""Immutable contracts for iterative, evidence-gated program repair."""

import fnmatch
import hashlib
import re
from dataclasses import asdict, dataclass
from enum import StrEnum

from archguard.domain.orchestration import AgentRole, ArtifactReference, fingerprint, valid_id
from archguard.domain.repository import check, digest, safe_path

REPAIR_TASK_SCHEMA = "archguard.repair-task/v1"
PATCH_CANDIDATE_SCHEMA = "archguard.patch-candidate/v1"
REPAIR_FEEDBACK_SCHEMA = "archguard.repair-feedback/v1"
REPAIR_RESULT_SCHEMA = "archguard.repair-result/v1"
LINEAGE_SCHEMA = "archguard.candidate-lineage/v1"
DEFAULT_PROTECTED = (
    ".git/**",
    ".github/workflows/**",
    ".env*",
    ".archguard/**",
    "**/*gold*",
    "**/*solution*",
    "**/architecture*.yaml",
    "**/execution-plan*.yaml",
    "Dockerfile*",
    "docker-compose*.yml",
    "uv.lock",
    "poetry.lock",
    "package-lock.json",
    "pytest.ini",
    "pyproject.toml",
)


@dataclass(frozen=True)
class RepairBudget:
    rounds: int
    candidates_per_round: int
    total_candidates: int
    provider_invocations: int
    validations: int
    input_units: int
    output_units: int

    def __post_init__(self) -> None:
        values = asdict(self).values()
        check(
            all(isinstance(value, int) and 1 <= value <= 1_000_000 for value in values),
            "invalid repair budget",
        )
        check(self.candidates_per_round <= self.total_candidates, "contradictory candidate budget")


@dataclass(frozen=True)
class PatchPolicy:
    allowed_patterns: tuple[str, ...]
    prohibited_patterns: tuple[str, ...] = DEFAULT_PROTECTED
    protected_paths: tuple[str, ...] = ()
    maximum_changed_files: int = 8
    maximum_added_lines: int = 500
    maximum_deleted_lines: int = 500
    maximum_patch_bytes: int = 256_000
    allow_test_changes: bool = False
    allow_lockfile_changes: bool = False

    def __post_init__(self) -> None:
        for pattern in (*self.allowed_patterns, *self.prohibited_patterns, *self.protected_paths):
            check(
                bool(pattern)
                and not pattern.startswith(("/", "\\"))
                and ".." not in pattern.split("/"),
                "invalid path policy",
            )
        check(bool(self.allowed_patterns), "empty allowed path policy")
        check(
            all(
                1 <= value <= 1_000_000
                for value in (
                    self.maximum_changed_files,
                    self.maximum_added_lines,
                    self.maximum_deleted_lines,
                    self.maximum_patch_bytes,
                )
            ),
            "invalid patch bound",
        )
        for protected in self.protected_paths:
            check(
                protected not in self.allowed_patterns,
                "protected path included in allowed paths",
            )


@dataclass(frozen=True)
class AcceptancePolicy:
    require_target_failures_fixed: bool = True
    require_no_regressions: bool = True
    require_architecture_pass: bool = True
    require_test_preservation: bool = True
    require_cleanup: bool = True
    first_success: bool = False

    def __post_init__(self) -> None:
        check(any(asdict(self).values()), "empty acceptance policy")
        check(
            self.require_no_regressions and self.require_architecture_pass,
            "mandatory validation disabled",
        )


@dataclass(frozen=True)
class RepairTask:
    schema: str
    task_id: str
    repository: str
    baseline_revision: str
    problem_statement: str
    failing_tests: tuple[str, ...]
    target_tests: tuple[str, ...]
    regression_scope: tuple[str, ...]
    architecture_profile: ArtifactReference
    repository_graph: ArtifactReference
    execution_plan: ArtifactReference
    patch_policy: PatchPolicy
    budget: RepairBudget
    provider_policy: str
    diversity_intents: tuple[str, ...]
    acceptance: AcceptancePolicy
    human_approval_required: bool
    mandatory_validation: bool = True
    trust_model_evidence: bool = False
    task_fingerprint: str = ""

    def __post_init__(self) -> None:
        check(self.schema == REPAIR_TASK_SCHEMA, "unsupported repair task schema")
        valid_id(self.task_id)
        safe_path(self.repository)
        check(
            re.fullmatch(r"[0-9a-f]{40}", self.baseline_revision) is not None,
            "invalid baseline revision",
        )
        check(0 < len(self.problem_statement) <= 64_000, "invalid problem statement")
        check(
            self.mandatory_validation and not self.trust_model_evidence,
            "validation bypass prohibited",
        )
        check(bool(self.provider_policy.strip()), "empty provider policy")
        object.__setattr__(self, "failing_tests", tuple(sorted(set(self.failing_tests))))
        object.__setattr__(self, "target_tests", tuple(sorted(set(self.target_tests))))
        object.__setattr__(self, "regression_scope", tuple(sorted(set(self.regression_scope))))
        object.__setattr__(self, "diversity_intents", tuple(sorted(set(self.diversity_intents))))
        expected = fingerprint(
            {key: value for key, value in asdict(self).items() if key != "task_fingerprint"}
        )
        if self.task_fingerprint:
            check(self.task_fingerprint == expected, "task fingerprint mismatch")
        else:
            object.__setattr__(self, "task_fingerprint", expected)


class RepairIntent(StrEnum):
    MINIMAL_LOCAL_FIX = "minimal_local_fix"
    CONTROL_FLOW = "control_flow_correction"
    DATA_VALIDATION = "data_validation_correction"
    API_CONTRACT = "api_contract_correction"
    ARCHITECTURE_REFACTOR = "architecture_preserving_refactor"


@dataclass(frozen=True)
class PatchCandidate:
    schema: str
    candidate_id: str
    run_id: str
    task_fingerprint: str
    repair_round: int
    parent_candidate_id: str | None
    generating_role: AgentRole
    provider_invocation: ArtifactReference
    raw_patch: ArtifactReference
    normalized_patch_fingerprint: str
    semantic_candidate_fingerprint: str
    changed_paths: tuple[str, ...]
    added_lines: int
    deleted_lines: int
    intent: RepairIntent
    assumptions: tuple[str, ...]
    sensitivity: str = "source_sensitive"

    def __post_init__(self) -> None:
        check(self.schema == PATCH_CANDIDATE_SCHEMA, "unsupported candidate schema")
        valid_id(self.candidate_id)
        valid_id(self.run_id)
        digest(self.task_fingerprint)
        digest(self.normalized_patch_fingerprint)
        check(self.repair_round >= 1, "invalid repair round")
        if self.parent_candidate_id:
            valid_id(self.parent_candidate_id)
            check(self.parent_candidate_id != self.candidate_id, "self-parent candidate")
        paths = tuple(sorted(set(self.changed_paths)))
        check(paths == self.changed_paths and bool(paths), "invalid changed paths")
        for path in paths:
            safe_path(path)
        check(
            0 <= self.added_lines <= 1_000_000 and 0 <= self.deleted_lines <= 1_000_000,
            "invalid line statistics",
        )
        check(self.sensitivity in {"source_sensitive", "source_free"}, "invalid sensitivity")
        expected = fingerprint(
            {
                "task": self.task_fingerprint,
                "patch": self.normalized_patch_fingerprint,
                "paths": paths,
            }
        )
        check(
            self.semantic_candidate_fingerprint == expected,
            "semantic candidate fingerprint mismatch",
        )


class PrecheckCode(StrEnum):
    MALFORMED = "malformed_patch"
    PROTECTED_PATH = "protected_path"
    OUTSIDE_SCOPE = "outside_allowed_scope"
    TOO_MANY_FILES = "too_many_changed_files"
    TOO_MANY_LINES = "line_change_limit"
    TOO_LARGE = "patch_byte_limit"
    FORBIDDEN_CHANGE = "forbidden_validation_change"
    DUPLICATE = "duplicate_candidate"
    INVALID_LINEAGE = "invalid_lineage"


@dataclass(frozen=True)
class PrecheckResult:
    accepted: bool
    reasons: tuple[PrecheckCode, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", tuple(sorted(set(self.reasons))))
        check(self.accepted == (not self.reasons), "invalid precheck result")


class RepairLoopState(StrEnum):
    TASK_VALIDATED = "task_validated"
    CONTEXT_PREPARED = "context_prepared"
    ROUND_STARTED = "round_started"
    CANDIDATES_REQUESTED = "candidates_requested"
    CANDIDATE_RECEIVED = "candidate_received"
    CANDIDATE_PRECHECKED = "candidate_prechecked"
    CANDIDATE_VALIDATING = "candidate_validating"
    FEEDBACK_PREPARED = "feedback_prepared"
    REFINEMENT_REQUESTED = "refinement_requested"
    ROUND_COMPLETED = "round_completed"
    CONVERGED = "converged"
    CANDIDATE_SELECTED = "candidate_selected"
    NO_ACCEPTABLE_CANDIDATE = "no_acceptable_candidate"
    BUDGET_EXHAUSTED = "budget_exhausted"
    AWAITING_HUMAN_APPROVAL = "awaiting_human_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_LOOP_STATES = frozenset(
    {
        RepairLoopState.COMPLETED,
        RepairLoopState.NO_ACCEPTABLE_CANDIDATE,
        RepairLoopState.BUDGET_EXHAUSTED,
        RepairLoopState.FAILED,
        RepairLoopState.CANCELLED,
    }
)


@dataclass(frozen=True)
class ValidationEvidence:
    candidate_id: str
    applicable: bool
    analysis_complete: bool
    architecture_passed: bool
    introduced_architecture_errors: int
    regressions: int
    target_failures_fixed: int
    persistent_failures: int
    required_tests_preserved: bool
    timed_out: bool
    infrastructure_failure: bool
    cleanup_succeeded: bool
    patch_bytes: int
    changed_files: int
    evidence_fingerprint: str = ""

    def __post_init__(self) -> None:
        valid_id(self.candidate_id)
        counts = (
            self.introduced_architecture_errors,
            self.regressions,
            self.target_failures_fixed,
            self.persistent_failures,
            self.patch_bytes,
            self.changed_files,
        )
        check(
            all(isinstance(value, int) and value >= 0 for value in counts),
            "invalid validation evidence",
        )
        expected = fingerprint(
            {key: value for key, value in asdict(self).items() if key != "evidence_fingerprint"}
        )
        if self.evidence_fingerprint:
            check(self.evidence_fingerprint == expected, "evidence fingerprint mismatch")
        else:
            object.__setattr__(self, "evidence_fingerprint", expected)

    def accepted(self, policy: AcceptancePolicy) -> bool:
        return (
            self.applicable
            and self.analysis_complete
            and self.architecture_passed
            and self.introduced_architecture_errors == 0
            and (not policy.require_no_regressions or self.regressions == 0)
            and (not policy.require_target_failures_fixed or self.persistent_failures == 0)
            and (not policy.require_test_preservation or self.required_tests_preserved)
            and not self.timed_out
            and not self.infrastructure_failure
            and (not policy.require_cleanup or self.cleanup_succeeded)
        )


@dataclass(frozen=True)
class RepairFeedback:
    schema: str
    candidate_id: str
    stage: str
    rejection_categories: tuple[str, ...]
    failing_tests: tuple[str, ...]
    bounded_excerpt: str
    remaining_rounds: int
    remaining_validations: int
    allowed_next_actions: tuple[str, ...]
    feedback_fingerprint: str = ""

    def __post_init__(self) -> None:
        check(self.schema == REPAIR_FEEDBACK_SCHEMA, "unsupported feedback schema")
        valid_id(self.candidate_id)
        check(len(self.bounded_excerpt.encode()) <= 4096, "feedback excerpt too large")
        check(
            "/Users/" not in self.bounded_excerpt and "api_key" not in self.bounded_excerpt.lower(),
            "unsafe feedback",
        )
        for name in ("rejection_categories", "failing_tests", "allowed_next_actions"):
            object.__setattr__(self, name, tuple(sorted(set(getattr(self, name)))))
        expected = fingerprint(
            {key: value for key, value in asdict(self).items() if key != "feedback_fingerprint"}
        )
        if self.feedback_fingerprint:
            check(self.feedback_fingerprint == expected, "feedback fingerprint mismatch")
        else:
            object.__setattr__(self, "feedback_fingerprint", expected)


@dataclass(frozen=True)
class CandidateLineage:
    schema: str
    run_id: str
    candidates: tuple[PatchCandidate, ...]
    duplicates: tuple[tuple[str, str], ...] = ()
    selected_candidate_id: str | None = None
    lineage_fingerprint: str = ""

    def __post_init__(self) -> None:
        check(self.schema == LINEAGE_SCHEMA, "unsupported lineage schema")
        valid_id(self.run_id)
        ordered = tuple(sorted(self.candidates, key=lambda item: item.candidate_id))
        check(ordered == self.candidates, "unordered lineage")
        by_id = {item.candidate_id: item for item in ordered}
        check(len(by_id) == len(ordered), "duplicate candidate ID")
        for item in ordered:
            check(item.run_id == self.run_id, "cross-run candidate")
            if item.parent_candidate_id:
                check(item.parent_candidate_id in by_id, "missing candidate parent")
                check(
                    by_id[item.parent_candidate_id].repair_round < item.repair_round,
                    "candidate lineage cycle",
                )
        if self.selected_candidate_id:
            check(self.selected_candidate_id in by_id, "unknown selected candidate")
        normalized_duplicates = tuple(sorted(set(self.duplicates)))
        check(normalized_duplicates == self.duplicates, "unordered duplicate relationships")
        expected = fingerprint(
            {key: value for key, value in asdict(self).items() if key != "lineage_fingerprint"}
        )
        if self.lineage_fingerprint:
            check(self.lineage_fingerprint == expected, "lineage fingerprint mismatch")
        else:
            object.__setattr__(self, "lineage_fingerprint", expected)


class RepairStatus(StrEnum):
    REPAIRED = "repaired"
    NO_ACCEPTABLE_CANDIDATE = "no_acceptable_candidate"
    AWAITING_HUMAN_APPROVAL = "awaiting_human_approval"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CANCELLED = "cancelled"
    INFRASTRUCTURE_FAILURE = "infrastructure_failure"
    INVALID_TASK = "invalid_task"
    PARTIAL = "partial"


@dataclass(frozen=True)
class RepairResult:
    schema: str
    task_fingerprint: str
    run_id: str
    status: RepairStatus
    stop_reason: str
    selected_candidate_id: str | None
    ranked_candidates: tuple[str, ...]
    rejected_candidates: tuple[tuple[str, tuple[str, ...]], ...]
    lineage_fingerprint: str
    validation_evidence: tuple[str, ...]
    provider_invocations: tuple[str, ...]
    known_limitations: tuple[str, ...]
    result_fingerprint: str = ""

    def __post_init__(self) -> None:
        check(self.schema == REPAIR_RESULT_SCHEMA, "unsupported repair result schema")
        digest(self.task_fingerprint)
        digest(self.lineage_fingerprint)
        valid_id(self.run_id)
        check(bool(self.stop_reason), "missing stop reason")
        if self.status == RepairStatus.REPAIRED:
            check(self.selected_candidate_id is not None, "repaired result lacks candidate")
        expected = fingerprint(
            {key: value for key, value in asdict(self).items() if key != "result_fingerprint"}
        )
        if self.result_fingerprint:
            check(self.result_fingerprint == expected, "result fingerprint mismatch")
        else:
            object.__setattr__(self, "result_fingerprint", expected)


def normalized_patch(raw: bytes) -> bytes:
    check(b"\0" not in raw, "patch contains NUL")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("patch is not UTF-8") from None
    check(not text.startswith("```") and "\n```" not in text, "Markdown patch wrapper prohibited")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    check(normalized.startswith("diff --git "), "patch contains prose or malformed prefix")
    return (normalized.rstrip("\n") + "\n").encode()


def patch_stats(raw: bytes) -> tuple[int, int]:
    added = deleted = 0
    for line in raw.splitlines():
        if line.startswith(b"+") and not line.startswith(b"+++"):
            added += 1
        elif line.startswith(b"-") and not line.startswith(b"---"):
            deleted += 1
    return added, deleted


def semantic_candidate_fingerprint(
    task_fingerprint: str, patch_fingerprint: str, paths: tuple[str, ...]
) -> str:
    return fingerprint(
        {"task": task_fingerprint, "patch": patch_fingerprint, "paths": tuple(sorted(paths))}
    )


def raw_fingerprint(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def path_allowed(path: str, policy: PatchPolicy) -> bool:
    allowed = any(fnmatch.fnmatch(path, pattern) for pattern in policy.allowed_patterns)
    blocked = any(fnmatch.fnmatch(path, pattern) for pattern in policy.prohibited_patterns) or any(
        path == item or path.startswith(item.rstrip("/") + "/") for item in policy.protected_paths
    )
    if not policy.allow_test_changes and (path.startswith("tests/") or "/tests/" in path):
        blocked = True
    if not policy.allow_lockfile_changes and path.rsplit("/", 1)[-1] in {
        "uv.lock",
        "poetry.lock",
        "package-lock.json",
    }:
        blocked = True
    return allowed and not blocked


def forbidden_change(raw: bytes) -> bool:
    lowered = raw.lower()
    tokens = (
        b"@pytest.mark.skip",
        b"pytest.skip(",
        b"xfail",
        b"--cov-fail-under=0",
        b"|| true",
        b"assert true",
        b"network_mode: host",
        b"privileged: true",
    )
    return any(token in lowered for token in tokens)


def rank_validated(
    candidates: tuple[tuple[PatchCandidate, ValidationEvidence], ...], policy: AcceptancePolicy
) -> tuple[str, ...]:
    eligible = [
        (candidate, evidence) for candidate, evidence in candidates if evidence.accepted(policy)
    ]
    eligible.sort(
        key=lambda pair: (
            -int(pair[1].accepted(policy)),
            pair[1].regressions,
            -pair[1].target_failures_fixed,
            pair[1].persistent_failures,
            pair[1].introduced_architecture_errors,
            pair[1].patch_bytes,
            pair[1].changed_files,
            pair[0].repair_round,
            pair[0].semantic_candidate_fingerprint,
        )
    )
    return tuple(candidate.candidate_id for candidate, _ in eligible)
