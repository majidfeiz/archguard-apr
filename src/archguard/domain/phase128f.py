"""Phase 12.8F sandboxed evaluator-qualification contracts."""

import re
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import PurePosixPath

from archguard.domain.orchestration import fingerprint, valid_id
from archguard.domain.readiness import git_sha1_commit, sha256_digest
from archguard.domain.repository import check

ADAPTER_SCHEMA = "archguard.evaluator-adapter/v3"
LEGACY_ADAPTER_SCHEMA = "archguard.evaluator-adapter/v2"
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
    FIXED_CONTROL_FAILED = "FIXED_CONTROL_FAILED"
    FIXED_CONTROL_INFRASTRUCTURE_FAILURE = "FIXED_CONTROL_INFRASTRUCTURE_FAILURE"
    EVALUATOR_ADAPTER_INVALID = "EVALUATOR_ADAPTER_INVALID"
    EVALUATOR_ENVIRONMENT_INVALID = "EVALUATOR_ENVIRONMENT_INVALID"


class FixedControlStage(StrEnum):
    ACQUISITION = "ACQUISITION"
    REVISION_VALIDATION = "REVISION_VALIDATION"
    DEPENDENCY_RESOLUTION = "DEPENDENCY_RESOLUTION"
    IMAGE_BUILD = "IMAGE_BUILD"
    PROJECT_INSTALL = "PROJECT_INSTALL"
    TEST_COLLECTION = "TEST_COLLECTION"
    TEST_EXECUTION = "TEST_EXECUTION"
    RESULT_PARSING = "RESULT_PARSING"
    CLEANUP = "CLEANUP"


class Outcome(StrEnum):
    PASS = "PASS"
    EXPECTED_FAILURE = "EXPECTED_FAILURE"
    OTHER_FAILURE = "OTHER_FAILURE"
    TIMEOUT = "TIMEOUT"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    ENVIRONMENT_FAILURE = "ENVIRONMENT_FAILURE"
    INFRASTRUCTURE_FAILURE = "INFRASTRUCTURE_FAILURE"


class EvaluatorValidationStatus(StrEnum):
    VALID = "VALID"
    EVALUATOR_ADAPTER_INVALID = "EVALUATOR_ADAPTER_INVALID"
    EVALUATOR_ENVIRONMENT_INVALID = "EVALUATOR_ENVIRONMENT_INVALID"
    SELECTOR_INCOMPATIBLE_ACROSS_REVISIONS = "SELECTOR_INCOMPATIBLE_ACROSS_REVISIONS"
    TEST_NOT_COLLECTED = "TEST_NOT_COLLECTED"
    PROJECT_NOT_INSTALLED = "PROJECT_NOT_INSTALLED"
    DEPENDENCY_MISSING = "DEPENDENCY_MISSING"
    UNSUPPORTED_EVALUATOR_LAYOUT = "UNSUPPORTED_EVALUATOR_LAYOUT"
    TOX_ENVIRONMENT_MISSING = "TOX_ENVIRONMENT_MISSING"
    TOX_CONFIGURATION_INVALID = "TOX_CONFIGURATION_INVALID"
    OFFLINE_DEPENDENCY_MISSING = "OFFLINE_DEPENDENCY_MISSING"
    EVALUATOR_NOT_COLLECTED = "EVALUATOR_NOT_COLLECTED"
    SCIENTIFIC_TEST_FAILURE = "SCIENTIFIC_TEST_FAILURE"


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
    upstream_requirements_sha256: str
    upstream_requirements_empty: bool
    dependency_constraints: tuple[str, ...]
    constraint_set_fingerprint: str
    constraint_provenance: str
    evaluator_argv: tuple[str, ...]
    test_selectors: tuple[str, ...]
    expected_buggy_outcome: str
    fixed_success: str
    source_license_id: str
    source_license_sha256: str
    sandbox: SandboxContract
    buggy_test_selectors: tuple[str, ...] = ()
    fixed_test_selectors: tuple[str, ...] = ()
    evaluator_source_type: str = "PROJECT_REVISION"
    evaluator_provenance: str = ""
    installation_plan: tuple[str, ...] = ()
    working_directory: str = "/workspace"
    expected_framework: str = ""
    quarantine_policy: str = "NONE"
    review_status: str = "LEGACY"
    evaluator_fixture_path: str | None = None
    evaluator_fixture_sha256: str | None = None
    availability: str = "AVAILABLE"
    unavailable_reason: str | None = None
    fingerprint: str = ""

    def __post_init__(self) -> None:
        check(self.schema in {ADAPTER_SCHEMA, LEGACY_ADAPTER_SCHEMA}, "unsupported adapter schema")
        check(
            self.task_id in SELECTED_TASKS and self.task_id != "PySnooper-2", "unknown adapter task"
        )
        valid_id(self.task_id)
        check(self.repository.startswith("https://github.com/"), "official repository required")
        git_sha1_commit(self.buggy_revision)
        git_sha1_commit(self.fixed_revision)
        sha256_digest(self.upstream_requirements_sha256)
        sha256_digest(self.constraint_set_fingerprint)
        sha256_digest(self.source_license_sha256)
        check(
            bool(self.dependency_constraints)
            and all(
                re.fullmatch(r"[A-Za-z0-9_.-]+==[A-Za-z0-9_.+-]+", item)
                for item in self.dependency_constraints
            ),
            "exact dependency constraints required",
        )
        check(bool(self.evaluator_argv) and bool(self.test_selectors), "incomplete evaluator")
        check(
            self.evaluator_argv[:3]
            in {("python", "-m", "pytest"), ("python", "-m", "unittest"), ("python", "-m", "tox")},
            "unreviewed evaluator argv",
        )
        check(
            all(item and "\x00" not in item for item in self.evaluator_argv),
            "invalid evaluator argv",
        )
        check(
            self.constraint_set_fingerprint
            == fingerprint({"constraints": list(self.dependency_constraints)}),
            "constraint fingerprint mismatch",
        )
        check(
            self.constraint_provenance.startswith("BugsInPy@"), "unreviewed constraint provenance"
        )
        check(
            self.upstream_requirements_empty
            == (
                self.upstream_requirements_sha256
                == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
            ),
            "requirements empty-state mismatch",
        )
        check(self.expected_buggy_outcome == "TEST_FAILURE", "unsupported expected outcome")
        check(self.fixed_success == "EXIT_ZERO", "unsupported fixed-control condition")
        if self.schema == ADAPTER_SCHEMA:
            check(
                bool(self.buggy_test_selectors and self.fixed_test_selectors),
                "selector plans required",
            )
            check(self.expected_framework in {"pytest", "unittest", "tox"}, "invalid framework")
            check(self.working_directory.startswith("/workspace"), "invalid working directory")
            check(self.review_status == "REVIEWED", "adapter review required")
            check(bool(self.installation_plan), "installation plan required")
            if self.evaluator_source_type == "FIXED_REVISION_QUARANTINED_TEST":
                check(self.evaluator_fixture_path is not None, "fixture path required")
                assert self.evaluator_fixture_path is not None
                fixture_path = PurePosixPath(self.evaluator_fixture_path)
                check(
                    not fixture_path.is_absolute()
                    and ".." not in fixture_path.parts
                    and fixture_path.suffix == ".py",
                    "invalid fixture path",
                )
                sha256_digest(self.evaluator_fixture_sha256 or "")
        check(self.availability in {"AVAILABLE", "EVALUATOR_UNAVAILABLE"}, "invalid availability")
        check(
            (self.availability == "AVAILABLE") == (self.unavailable_reason is None),
            "availability contradiction",
        )
        identity_body = {key: value for key, value in asdict(self).items() if key != "fingerprint"}
        if self.schema == LEGACY_ADAPTER_SCHEMA:
            for key in (
                "buggy_test_selectors",
                "fixed_test_selectors",
                "evaluator_source_type",
                "evaluator_provenance",
                "installation_plan",
                "working_directory",
                "expected_framework",
                "quarantine_policy",
                "review_status",
                "evaluator_fixture_path",
                "evaluator_fixture_sha256",
            ):
                identity_body.pop(key)
        identity = fingerprint(identity_body)
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
    normalized_failure_class: str | None = None

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
    failure_classes = {attempt.normalized_failure_class for attempt in attempts}
    if outcomes == {Outcome.OTHER_FAILURE} and len(failure_classes) == 1:
        failure_class = next(iter(failure_classes))
        if failure_class in {"SELECTOR_NOT_FOUND", "COLLECTION_ERROR"}:
            return Classification.EVALUATOR_ADAPTER_INVALID
        if failure_class in {
            "IMPORT_ERROR",
            "PROJECT_INSTALLATION_ERROR",
            "PERMISSION_ERROR",
            "TEST_PROCESS_ERROR",
        }:
            return Classification.EVALUATOR_ENVIRONMENT_INVALID
    if outcomes == {Outcome.PASS}:
        return Classification.NOT_REPRODUCIBLE
    signatures = {attempt.failure_signature for attempt in attempts}
    if outcomes != {Outcome.EXPECTED_FAILURE} or None in signatures or len(signatures) != 1:
        return Classification.FLAKY
    if not fixed_control_passed:
        return Classification.FIXED_CONTROL_FAILED
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
