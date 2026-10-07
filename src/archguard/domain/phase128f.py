"""Phase 12.8F sandboxed evaluator-qualification contracts."""

from dataclasses import asdict, dataclass
from enum import StrEnum

from archguard.domain.orchestration import fingerprint, valid_id
from archguard.domain.readiness import git_sha1_commit, sha256_digest
from archguard.domain.repository import check

ADAPTER_SCHEMA = "archguard.evaluator-adapter/v1"
QUALIFICATION_SCHEMA = "archguard.qualification-evidence/v1"
SELECTED_TASKS = (
    "PySnooper-1",
    "black-1",
    "cookiecutter-4",
    "PySnooper-2",
    "black-2",
    "PySnooper-3",
    "black-3",
    "black-4",
)
BATCH_A = ("PySnooper-1", "PySnooper-3", "black-1", "cookiecutter-4")
BATCH_B = ("black-2", "black-3", "black-4")


class Classification(StrEnum):
    STABLE = "STABLE"
    FLAKY = "FLAKY"
    ENVIRONMENT_SENSITIVE = "ENVIRONMENT_SENSITIVE"
    NOT_REPRODUCIBLE = "NOT_REPRODUCIBLE"
    EVALUATOR_UNAVAILABLE = "EVALUATOR_UNAVAILABLE"
    UNSUPPORTED_ENVIRONMENT = "UNSUPPORTED_ENVIRONMENT"
    INFRASTRUCTURE_FAILURE = "INFRASTRUCTURE_FAILURE"
    SKIPPED_RESOURCE_LIMIT = "SKIPPED_RESOURCE_LIMIT"


class Outcome(StrEnum):
    PASS = "PASS"
    EXPECTED_FAILURE = "EXPECTED_FAILURE"
    OTHER_FAILURE = "OTHER_FAILURE"
    TIMEOUT = "TIMEOUT"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    ENVIRONMENT_FAILURE = "ENVIRONMENT_FAILURE"
    INFRASTRUCTURE_FAILURE = "INFRASTRUCTURE_FAILURE"


@dataclass(frozen=True)
class SandboxContract:
    cpus: int = 2
    memory_bytes: int = 2 * 1024**3
    pids: int = 256
    timeout_seconds: int = 1200
    output_bytes: int = 1024**2
    tmpfs_bytes: int = 256 * 1024**2
    network: str = "none"
    user: str = "non-root"
    read_only_root: bool = True
    drop_capabilities: bool = True
    no_new_privileges: bool = True
    docker_socket: bool = False
    source_read_only: bool = True

    def __post_init__(self) -> None:
        check(0 < self.cpus <= 2, "CPU limit exceeded")
        check(0 < self.memory_bytes <= 2 * 1024**3, "memory limit exceeded")
        check(0 < self.pids <= 256, "PID limit exceeded")
        check(0 < self.timeout_seconds <= 1200, "timeout exceeded")
        check(0 < self.output_bytes <= 1024**2, "output limit exceeded")
        check(self.network == "none", "evaluator network must be disabled")
        check(self.user == "non-root", "evaluator must be non-root")
        check(self.drop_capabilities and self.no_new_privileges, "sandbox hardening required")
        check(not self.docker_socket and self.source_read_only, "unsafe evaluator mount")


@dataclass(frozen=True)
class EvaluatorAdapter:
    schema: str
    task_id: str
    project: str
    repository: str
    buggy_revision: str
    fixed_revision: str
    python_version: str
    dependency_locator: str
    dependency_sha256: str
    dependency_constraints: tuple[str, ...]
    evaluator_entry_point: str
    test_selectors: tuple[str, ...]
    expected_buggy_outcome: str
    fixed_success: str
    source_license_id: str
    source_license_sha256: str
    sandbox: SandboxContract
    availability: str = "AVAILABLE"
    unavailable_reason: str | None = None
    fingerprint: str = ""

    def __post_init__(self) -> None:
        check(self.schema == ADAPTER_SCHEMA, "unsupported adapter schema")
        check(
            self.task_id in SELECTED_TASKS and self.task_id != "PySnooper-2", "unknown adapter task"
        )
        valid_id(self.task_id)
        check(self.repository.startswith("https://github.com/"), "official repository required")
        git_sha1_commit(self.buggy_revision)
        git_sha1_commit(self.fixed_revision)
        sha256_digest(self.dependency_sha256)
        sha256_digest(self.source_license_sha256)
        check(
            bool(self.dependency_constraints)
            and all("==" in item for item in self.dependency_constraints),
            "exact dependency constraints required",
        )
        check(
            bool(self.evaluator_entry_point) and bool(self.test_selectors), "incomplete evaluator"
        )
        check(self.expected_buggy_outcome == "TEST_FAILURE", "unsupported expected outcome")
        check(self.fixed_success == "EXIT_ZERO", "unsupported fixed-control condition")
        check(self.availability in {"AVAILABLE", "EVALUATOR_UNAVAILABLE"}, "invalid availability")
        check(
            (self.availability == "AVAILABLE") == (self.unavailable_reason is None),
            "availability contradiction",
        )
        identity = fingerprint(
            {key: value for key, value in asdict(self).items() if key != "fingerprint"}
        )
        object.__setattr__(self, "fingerprint", self.fingerprint or identity)
        check(self.fingerprint == identity, "adapter fingerprint mismatch")


@dataclass(frozen=True)
class AttemptEvidence:
    outcome: Outcome
    exit_code: int | None
    failure_signature: str | None
    tests_passed: int
    tests_failed: int
    duration_milliseconds: int
    output_truncated: bool = False

    def __post_init__(self) -> None:
        if self.failure_signature is not None:
            sha256_digest(self.failure_signature)
        check(self.tests_passed >= 0 and self.tests_failed >= 0, "invalid test counts")
        check(0 <= self.duration_milliseconds <= 1_200_000, "invalid duration")
        if self.outcome is Outcome.PASS:
            check(self.exit_code == 0 and self.tests_failed == 0, "contradictory passing attempt")


def classify(
    attempts: tuple[AttemptEvidence, ...],
    *,
    fixed_control_passed: bool,
    adapter_available: bool = True,
    environment_supported: bool = True,
) -> Classification:
    """Classify qualification evidence without repair or gold information."""
    if not adapter_available:
        return Classification.EVALUATOR_UNAVAILABLE
    if not environment_supported:
        return Classification.UNSUPPORTED_ENVIRONMENT
    check(len(attempts) == 3, "exactly three buggy attempts required")
    outcomes = {attempt.outcome for attempt in attempts}
    if Outcome.INFRASTRUCTURE_FAILURE in outcomes:
        return Classification.INFRASTRUCTURE_FAILURE
    if Outcome.RESOURCE_LIMIT in outcomes or Outcome.TIMEOUT in outcomes:
        return Classification.SKIPPED_RESOURCE_LIMIT
    if Outcome.ENVIRONMENT_FAILURE in outcomes:
        return Classification.ENVIRONMENT_SENSITIVE
    if outcomes == {Outcome.PASS}:
        return Classification.NOT_REPRODUCIBLE
    signatures = {attempt.failure_signature for attempt in attempts}
    if outcomes != {Outcome.EXPECTED_FAILURE} or None in signatures or len(signatures) != 1:
        return Classification.FLAKY
    if not fixed_control_passed:
        return Classification.ENVIRONMENT_SENSITIVE
    return Classification.STABLE


def qualification_decision(classification: Classification, fixed_control_passed: bool) -> str:
    if classification is Classification.STABLE:
        check(fixed_control_passed, "STABLE requires passing fixed control")
        return "QUALIFIED"
    return "NOT_QUALIFIED"


def prior_evidence_status(task_id: str, new: Classification) -> str:
    prior = {
        "PySnooper-1": Classification.NOT_REPRODUCIBLE,
        "PySnooper-2": Classification.STABLE,
    }
    if task_id not in prior:
        return "NO_PRIOR_EVIDENCE"
    return "CONSISTENT" if prior[task_id] is new else "EVIDENCE_CONFLICT_REVIEW_REQUIRED"
