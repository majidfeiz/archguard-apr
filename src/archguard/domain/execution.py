"""Immutable, source-free execution feedback contracts and functional comparison."""

import hashlib
import re
from dataclasses import asdict, dataclass
from enum import StrEnum
from math import isfinite

from archguard.domain.canonical import canonical_json
from archguard.domain.repository import check, digest, safe_path

EXECUTION_PLAN_SCHEMA = "archguard.execution-plan/v1"
EXECUTION_EVIDENCE_SCHEMA = "archguard.execution-evidence/v1"
FUNCTIONAL_DELTA_SCHEMA = "archguard.functional-delta/v1"
CANDIDATE_VALIDATION_SCHEMA = "archguard.candidate-validation/v1"
MAX_TIMEOUT_SECONDS = 3600
MAX_OUTPUT_BYTES = 16 * 1024 * 1024


class ResultAdapter(StrEnum):
    COMMAND = "command"
    JUNIT = "pytest-junit"


class FailurePolicy(StrEnum):
    STOP = "stop"
    CONTINUE = "continue"


class CommandState(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    INFRASTRUCTURE_ERROR = "infrastructure_error"
    INVALID_RESULT = "invalid_result"


class TestState(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"
    XFAIL = "xfail"
    XPASS = "xpass"


class DeltaState(StrEnum):
    FIXED = "fixed"
    REGRESSED = "regressed"
    PERSISTENT_FAILURE = "persistent_failure"
    PASSED_BOTH = "passed_both"
    CANDIDATE_ONLY = "candidate_only"
    BASELINE_ONLY = "baseline_only"
    STATUS_CHANGED = "status_changed"


def _identifier(value: str) -> None:
    check(
        bool(value) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value) is not None,
        "invalid identifier",
    )


def _fingerprint(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


@dataclass(frozen=True)
class ResourceLimits:
    cpu_count: float
    memory_bytes: int
    pid_limit: int
    temporary_storage_bytes: int
    maximum_output_bytes: int

    def __post_init__(self) -> None:
        check(isfinite(self.cpu_count) and 0 < self.cpu_count <= 32, "invalid CPU limit")
        check(16 * 1024 * 1024 <= self.memory_bytes <= 64 * 1024**3, "invalid memory limit")
        check(1 <= self.pid_limit <= 4096, "invalid PID limit")
        check(
            1024 * 1024 <= self.temporary_storage_bytes <= 16 * 1024**3,
            "invalid temporary-storage limit",
        )
        check(1 <= self.maximum_output_bytes <= MAX_OUTPUT_BYTES, "invalid output limit")


@dataclass(frozen=True)
class ValidationStage:
    stage_id: str
    argv: tuple[str, ...]
    working_directory: str
    timeout_seconds: int
    adapter: ResultAdapter
    expected_artifacts: tuple[str, ...] = ()
    failure_policy: FailurePolicy = FailurePolicy.STOP

    def __post_init__(self) -> None:
        _identifier(self.stage_id)
        object.__setattr__(self, "argv", tuple(self.argv))
        object.__setattr__(self, "expected_artifacts", tuple(self.expected_artifacts))
        check(bool(self.argv), "command must not be empty")
        for argument in self.argv:
            check(
                isinstance(argument, str) and bool(argument) and "\x00" not in argument,
                "invalid argv",
            )
        if self.working_directory != ".":
            safe_path(self.working_directory)
        check(0 < self.timeout_seconds <= MAX_TIMEOUT_SECONDS, "invalid command timeout")
        check(isinstance(self.adapter, ResultAdapter), "invalid result adapter")
        check(isinstance(self.failure_policy, FailurePolicy), "invalid failure policy")
        for path in self.expected_artifacts:
            safe_path(path)
        check(
            len(set(self.expected_artifacts)) == len(self.expected_artifacts),
            "duplicate expected artifact",
        )


@dataclass(frozen=True)
class ExecutionPlan:
    schema: str
    plan_id: str
    image: str
    stages: tuple[ValidationStage, ...]
    total_timeout_seconds: int
    limits: ResourceLimits
    allowed_environment: tuple[str, ...] = ()
    environment: tuple[tuple[str, str], ...] = ()
    target_tests: tuple[str, ...] = ()
    allow_persistent_failures: bool = False
    plan_fingerprint: str = ""

    def __post_init__(self) -> None:
        check(self.schema == EXECUTION_PLAN_SCHEMA, "unsupported execution-plan schema")
        _identifier(self.plan_id)
        check(
            re.fullmatch(r"(?:[^\s@]+@)?sha256:[0-9a-f]{64}", self.image) is not None,
            "container image must be pinned by SHA-256 digest",
        )
        object.__setattr__(self, "stages", tuple(self.stages))
        check(bool(self.stages), "plan must contain stages")
        check(
            len({stage.stage_id for stage in self.stages}) == len(self.stages), "duplicate stage ID"
        )
        check(0 < self.total_timeout_seconds <= MAX_TIMEOUT_SECONDS, "invalid total timeout")
        check(
            sum(stage.timeout_seconds for stage in self.stages) <= self.total_timeout_seconds,
            "stage timeouts exceed total timeout",
        )
        object.__setattr__(self, "allowed_environment", tuple(self.allowed_environment))
        object.__setattr__(self, "environment", tuple(tuple(item) for item in self.environment))
        object.__setattr__(self, "target_tests", tuple(sorted(set(self.target_tests))))
        for name in self.allowed_environment:
            check(re.fullmatch(r"[A-Z_][A-Z0-9_]*", name) is not None, "invalid environment name")
        check(
            len(set(self.allowed_environment)) == len(self.allowed_environment),
            "duplicate allowed environment",
        )
        for name, value in self.environment:
            check(
                re.fullmatch(r"[A-Z_][A-Z0-9_]*", name) is not None and "\x00" not in value,
                "invalid constant environment",
            )
        check(
            not set(self.allowed_environment) & {name for name, _ in self.environment},
            "environment declaration conflict",
        )
        expected = _fingerprint({k: v for k, v in asdict(self).items() if k != "plan_fingerprint"})
        if self.plan_fingerprint:
            digest(self.plan_fingerprint)
            check(self.plan_fingerprint == expected, "plan fingerprint mismatch")
        else:
            object.__setattr__(self, "plan_fingerprint", expected)


@dataclass(frozen=True, order=True)
class TestCaseObservation:
    test_id: str
    state: TestState

    def __post_init__(self) -> None:
        check(bool(self.test_id) and "\x00" not in self.test_id, "invalid test identity")
        check(isinstance(self.state, TestState), "invalid test state")


@dataclass(frozen=True)
class CommandObservation:
    stage_id: str
    command_index: int
    command_sha256: str
    state: CommandState
    exit_code: int | None
    stdout_sha256: str
    stderr_sha256: str
    stdout_truncated: bool
    stderr_truncated: bool
    artifacts_present: tuple[str, ...]
    artifacts_missing: tuple[str, ...]
    tests: tuple[TestCaseObservation, ...]
    diagnostic: str | None = None

    def __post_init__(self) -> None:
        _identifier(self.stage_id)
        check(self.command_index >= 0, "invalid command index")
        for value in (self.command_sha256, self.stdout_sha256, self.stderr_sha256):
            digest(value)
        check(isinstance(self.state, CommandState), "invalid command state")
        object.__setattr__(self, "artifacts_present", tuple(sorted(self.artifacts_present)))
        object.__setattr__(self, "artifacts_missing", tuple(sorted(self.artifacts_missing)))
        object.__setattr__(self, "tests", tuple(sorted(self.tests)))
        check(
            len({test.test_id for test in self.tests}) == len(self.tests), "duplicate test identity"
        )


@dataclass(frozen=True)
class ExecutionEvidence:
    schema: str
    plan_id: str
    plan_fingerprint: str
    observations: tuple[CommandObservation, ...]
    completed: bool
    infrastructure_healthy: bool
    evidence_fingerprint: str = ""

    def __post_init__(self) -> None:
        check(self.schema == EXECUTION_EVIDENCE_SCHEMA, "unsupported execution-evidence schema")
        _identifier(self.plan_id)
        digest(self.plan_fingerprint)
        object.__setattr__(self, "observations", tuple(self.observations))
        expected = _fingerprint(
            {k: v for k, v in asdict(self).items() if k != "evidence_fingerprint"}
        )
        if self.evidence_fingerprint:
            check(self.evidence_fingerprint == expected, "evidence fingerprint mismatch")
        else:
            object.__setattr__(self, "evidence_fingerprint", expected)


@dataclass(frozen=True, order=True)
class TestTransition:
    test_id: str
    state: DeltaState
    baseline_state: TestState | None
    candidate_state: TestState | None


@dataclass(frozen=True)
class FunctionalDelta:
    schema: str
    baseline_evidence_fingerprint: str
    candidate_evidence_fingerprint: str
    transitions: tuple[TestTransition, ...]
    accepted: bool
    rejection_reasons: tuple[str, ...]
    delta_fingerprint: str = ""

    def __post_init__(self) -> None:
        check(self.schema == FUNCTIONAL_DELTA_SCHEMA, "unsupported functional-delta schema")
        digest(self.baseline_evidence_fingerprint)
        digest(self.candidate_evidence_fingerprint)
        object.__setattr__(self, "transitions", tuple(sorted(self.transitions)))
        object.__setattr__(self, "rejection_reasons", tuple(sorted(set(self.rejection_reasons))))
        expected = _fingerprint({k: v for k, v in asdict(self).items() if k != "delta_fingerprint"})
        if self.delta_fingerprint:
            check(self.delta_fingerprint == expected, "delta fingerprint mismatch")
        else:
            object.__setattr__(self, "delta_fingerprint", expected)


def compare_evidence(
    baseline: ExecutionEvidence, candidate: ExecutionEvidence, plan: ExecutionPlan
) -> FunctionalDelta:
    def indexed(value: ExecutionEvidence) -> dict[str, TestState]:
        return {test.test_id: test.state for obs in value.observations for test in obs.tests}

    before, after = indexed(baseline), indexed(candidate)
    passing = {TestState.PASSED, TestState.XPASS}
    failing = {TestState.FAILED, TestState.ERROR}
    transitions: list[TestTransition] = []
    for test_id in sorted(before.keys() | after.keys()):
        left, right = before.get(test_id), after.get(test_id)
        if left is None:
            state = DeltaState.CANDIDATE_ONLY
        elif right is None:
            state = DeltaState.BASELINE_ONLY
        elif left in failing and right in passing:
            state = DeltaState.FIXED
        elif left in passing and right in failing:
            state = DeltaState.REGRESSED
        elif left in failing and right in failing:
            state = DeltaState.PERSISTENT_FAILURE
        elif left in passing and right in passing:
            state = DeltaState.PASSED_BOTH
        else:
            state = DeltaState.STATUS_CHANGED
        transitions.append(TestTransition(test_id, state, left, right))
    reasons: set[str] = set()
    if not baseline.infrastructure_healthy or not candidate.infrastructure_healthy:
        reasons.add("infrastructure_unhealthy")
    if not baseline.completed or not candidate.completed:
        reasons.add("execution_incomplete")
    states = {item.state for item in transitions}
    if DeltaState.REGRESSED in states:
        reasons.add("regression")
    if DeltaState.BASELINE_ONLY in states:
        reasons.add("baseline_test_missing")
    if not plan.allow_persistent_failures and DeltaState.PERSISTENT_FAILURE in states:
        reasons.add("persistent_failure")
    if plan.target_tests and not any(
        item.state == DeltaState.FIXED and item.test_id in plan.target_tests for item in transitions
    ):
        reasons.add("target_not_fixed")
    return FunctionalDelta(
        FUNCTIONAL_DELTA_SCHEMA,
        baseline.evidence_fingerprint,
        candidate.evidence_fingerprint,
        tuple(transitions),
        not reasons,
        tuple(reasons),
    )


@dataclass(frozen=True)
class CandidateValidationReport:
    schema: str
    patch_validation_fingerprint: str
    baseline_evidence_fingerprint: str
    candidate_evidence_fingerprint: str
    functional_delta_fingerprint: str
    patch_applicable: bool
    architecture_accepted: bool
    functional_accepted: bool
    infrastructure_healthy: bool
    overall_accepted: bool
    context_manifest_fingerprint: str | None = None
    report_fingerprint: str = ""

    def __post_init__(self) -> None:
        check(self.schema == CANDIDATE_VALIDATION_SCHEMA, "unsupported validation schema")
        for value in (
            self.patch_validation_fingerprint,
            self.baseline_evidence_fingerprint,
            self.candidate_evidence_fingerprint,
            self.functional_delta_fingerprint,
        ):
            digest(value)
        if self.context_manifest_fingerprint is not None:
            digest(self.context_manifest_fingerprint)
        check(
            self.overall_accepted
            == all(
                (
                    self.patch_applicable,
                    self.architecture_accepted,
                    self.functional_accepted,
                    self.infrastructure_healthy,
                )
            ),
            "invalid overall acceptance",
        )
        expected = _fingerprint(
            {k: v for k, v in asdict(self).items() if k != "report_fingerprint"}
        )
        if self.report_fingerprint:
            check(self.report_fingerprint == expected, "report fingerprint mismatch")
        else:
            object.__setattr__(self, "report_fingerprint", expected)
