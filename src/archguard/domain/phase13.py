"""Frozen Phase 13 schedule, source-free outcomes, and cost state."""

from dataclasses import asdict, dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any

from archguard.domain.orchestration import fingerprint
from archguard.domain.repository import check, digest

POPULATION_FINGERPRINT = "421f3129ef6bee5883c41d05f087d6faff5b2a3de3b2ea543b4d27ade1488886"
PROVIDER_FINGERPRINT = "f5dc6fb5b8bf54c7cf1b58b990fa3db44073500df9903e3a7d93cbeb1ad92c2d"
MODEL = "gpt-5.4-2026-03-05"
RESULT_SCHEMA = "archguard.phase-13-execution/v1"


class Condition(StrEnum):
    BASELINE = "baseline"
    ARCHGUARD = "archguard"


class TerminalClassification(StrEnum):
    SUCCESS = "success"
    REPAIR_FAILURE = "repair_failure"
    INVALID_PATCH = "invalid_patch"
    UNSAFE_PATCH = "unsafe_patch"
    PROVIDER_FAILURE = "provider_failure"
    EVALUATOR_FAILURE = "evaluator_failure"
    COST_STOP = "cost_stop"
    PATCH_APPLICATION_FAILED = "patch_application_failed"
    ARCHITECTURE_VIOLATION = "architecture_violation"
    TESTS_FAILED = "tests_failed"
    REPAIR_UNSUCCESSFUL = "repair_unsuccessful"


class ResumeStopReason(StrEnum):
    """Checkpoint stop reasons with an explicit continuation policy."""

    EXECUTION_FAILURE = "execution_failure"
    AUTHENTICATION_FAILURE = "authentication_failure"
    BILLING_FAILURE = "billing_failure"
    QUOTA_FAILURE = "quota_failure"
    BUDGET_CEILING = "budget_ceiling"
    IDENTITY_MISMATCH = "fingerprint_protocol_population_provider_mismatch"
    LEAKAGE_OR_SECURITY_FAILURE = "leakage_security_failure"
    CORRUPT_CHECKPOINT = "corrupt_checkpoint"
    INCOMPLETE_CLEANUP = "incomplete_cleanup"


class ResumeStopClassification(StrEnum):
    """Auditable classification assigned to a historical stop."""

    CORRECTED_TERMINAL_OUTCOME_BUG = "corrected_terminal_outcome_bug"
    FATAL = "fatal"


@dataclass(frozen=True)
class ResumePolicy:
    historical_stop_reason: ResumeStopReason
    active_stop_reason: ResumeStopReason | None
    resume_allowed: bool


def classify_resume_stop(
    reason: ResumeStopReason, classification: ResumeStopClassification
) -> ResumePolicy:
    """Clear only the reviewed historical stop caused by the corrected runner bug."""
    if (
        reason is ResumeStopReason.EXECUTION_FAILURE
        and classification is ResumeStopClassification.CORRECTED_TERMINAL_OUTCOME_BUG
    ):
        return ResumePolicy(reason, None, True)
    return ResumePolicy(reason, reason, False)


@dataclass(frozen=True, order=True)
class ExecutionIdentity:
    ordinal: int
    task_id: str
    project: str
    condition: Condition


FROZEN_EXECUTIONS = (
    ExecutionIdentity(1, "PySnooper-2", "PySnooper", Condition.BASELINE),
    ExecutionIdentity(2, "PySnooper-2", "PySnooper", Condition.ARCHGUARD),
    ExecutionIdentity(3, "PySnooper-3", "PySnooper", Condition.BASELINE),
    ExecutionIdentity(4, "PySnooper-3", "PySnooper", Condition.ARCHGUARD),
    ExecutionIdentity(5, "black-4", "Black", Condition.BASELINE),
    ExecutionIdentity(6, "black-4", "Black", Condition.ARCHGUARD),
)


def validate_frozen_executions(values: tuple[ExecutionIdentity, ...]) -> None:
    check(values == FROZEN_EXECUTIONS, "Phase 13 execution schedule drift")
    check(len(values) == 6, "Phase 13 requires exactly six primary executions")


@dataclass(frozen=True)
class ProviderUsage:
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_tokens: int

    def __post_init__(self) -> None:
        values = asdict(self).values()
        check(all(isinstance(value, int) and value >= 0 for value in values), "invalid usage")
        check(self.cached_input_tokens <= self.input_tokens, "invalid cached usage")
        check(self.reasoning_tokens <= self.output_tokens, "invalid reasoning usage")


@dataclass(frozen=True)
class CostState:
    observed_usd: Decimal = Decimal("0")
    reserved_usd: Decimal = Decimal("0")
    completed_primary: int = 0
    attempted_retries: int = 0
    provider_calls_started: int = 0
    provider_calls_completed: int = 0
    provider_calls_with_usage: int = 0
    call_ids: tuple[str, ...] = ()
    stop_reason: str | None = "not_started"

    def __post_init__(self) -> None:
        check(self.observed_usd >= 0 and self.reserved_usd >= 0, "negative cost")
        check(0 <= self.completed_primary <= 6, "invalid primary count")
        check(0 <= self.attempted_retries <= 6, "invalid retry count")
        check(
            0 <= self.provider_calls_with_usage <= self.provider_calls_completed,
            "invalid usage call count",
        )
        check(
            self.provider_calls_completed <= self.provider_calls_started <= 12, "invalid call count"
        )
        check(len(self.call_ids) == self.provider_calls_started, "call ledger mismatch")
        check(len(set(self.call_ids)) == len(self.call_ids), "duplicate provider call identity")

    @property
    def calls_started(self) -> int:
        """Compatibility accessor for the original counter name."""
        return self.provider_calls_started


@dataclass(frozen=True)
class ExecutionResult:
    experiment_id: str
    identity: ExecutionIdentity
    immutable_buggy_revision: str
    protocol_fingerprint: str
    request_fingerprint: str
    context_manifest_fingerprint: str
    response_fingerprint: str
    patch_fingerprint: str
    patch_parsed: bool
    patch_applied: bool
    files_changed: int
    lines_added: int
    lines_deleted: int
    unsafe_patch_rejection: str | None
    architecture_status: str
    architecture_violations: tuple[tuple[str, int], ...]
    evaluator_executed: bool
    buggy_failure_reproduced: bool
    candidate_test_outcome: str
    tests_fixed: int
    regressions: int
    repair_success: bool
    terminal_classification: TerminalClassification
    usage: ProviderUsage
    observed_usd: Decimal
    attempt_count: int
    duration_bucket: str
    cleanup_status: str
    provider_call_id: str = ""

    def __post_init__(self) -> None:
        for value in (
            self.protocol_fingerprint,
            self.request_fingerprint,
            self.context_manifest_fingerprint,
            self.response_fingerprint,
            self.patch_fingerprint,
        ):
            digest(value)
        check(self.identity in FROZEN_EXECUTIONS, "unknown execution identity")
        check(self.architecture_status in {"passed", "partial", "skipped"}, "bad status")
        check(self.attempt_count in {1, 2}, "invalid attempt count")
        check(self.cleanup_status == "complete", "cleanup incomplete")
        if self.provider_call_id:
            digest(self.provider_call_id)

    def source_free_record(self) -> dict[str, Any]:
        return {
            "schema": RESULT_SCHEMA,
            "experiment_id": self.experiment_id,
            "run_ordinal": self.identity.ordinal,
            "task_id": self.identity.task_id,
            "project": self.identity.project,
            "condition": self.identity.condition.value,
            "immutable_buggy_revision": self.immutable_buggy_revision,
            "population_fingerprint": POPULATION_FINGERPRINT,
            "protocol_fingerprint": self.protocol_fingerprint,
            "provider_configuration_fingerprint": PROVIDER_FINGERPRINT,
            "model_snapshot": MODEL,
            **{
                key: _json_value(value)
                for key, value in asdict(self).items()
                if key
                not in {
                    "experiment_id",
                    "identity",
                    "immutable_buggy_revision",
                    "protocol_fingerprint",
                }
                and (key != "provider_call_id" or bool(value))
            },
        }


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def experiment_id(protocol_fingerprint: str) -> str:
    digest(protocol_fingerprint)
    return fingerprint(
        {
            "population": POPULATION_FINGERPRINT,
            "protocol": protocol_fingerprint,
            "provider": PROVIDER_FINGERPRINT,
            "executions": [asdict(item) for item in FROZEN_EXECUTIONS],
        }
    )
