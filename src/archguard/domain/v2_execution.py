"""Frozen, provider-neutral contracts for the bounded V2.2 micro-pilot."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from enum import StrEnum

from archguard.domain.providers import ProviderResponseState
from archguard.domain.repository import check, digest
from archguard.domain.v2_micro_pilot import (
    HARD_CEILING,
    MAX_CALLS,
    PER_CALL_RESERVATION,
    TOTAL_RESERVATION,
    SyntheticUsage,
)

TASKS = ("PySnooper-2", "PySnooper-3")
CONDITIONS = ("BASELINE", "GRAPH_ONLY", "GRAPH_CONSTRAINTS", "FULL_ARCHGUARD")
CALL_ORDER = tuple((task, condition) for task in TASKS for condition in CONDITIONS)


class ExecutionStatus(StrEnum):
    PENDING = "PENDING"
    RESERVED = "RESERVED"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class StageStatus(StrEnum):
    NOT_RUN = "NOT_RUN"
    PASSED = "PASSED"
    FAILED = "FAILED"
    NOT_REQUIRED = "NOT_REQUIRED"


class TerminalClassification(StrEnum):
    EXTRACTION_FAILURE = "EXTRACTION_FAILURE"
    INVALID_PATCH = "INVALID_PATCH"
    POLICY_REJECTION = "POLICY_REJECTION"
    APPLICATION_FAILURE = "APPLICATION_FAILURE"
    TEST_FAILURE = "TEST_FAILURE"
    ARCHITECTURE_VIOLATION = "ARCHITECTURE_VIOLATION"
    SUCCESSFUL_REPAIR = "SUCCESSFUL_REPAIR"
    INFRASTRUCTURE_FAILURE = "INFRASTRUCTURE_FAILURE"


class ProviderFailureKind(StrEnum):
    AUTHENTICATION = "AUTHENTICATION"
    PERMISSION_MODEL_ACCESS = "PERMISSION_MODEL_ACCESS"
    INVALID_REQUEST = "INVALID_REQUEST"
    SCHEMA_REJECTION = "SCHEMA_REJECTION"
    RATE_LIMIT = "RATE_LIMIT"
    NETWORK_TRANSPORT = "NETWORK_TRANSPORT"
    SERVER_ERROR = "SERVER_ERROR"
    UNKNOWN_PROVIDER_FAILURE = "UNKNOWN_PROVIDER_FAILURE"


@dataclass(frozen=True)
class ExecutionIdentity:
    ordinal: int
    task_id: str
    condition: str

    def __post_init__(self) -> None:
        check(1 <= self.ordinal <= MAX_CALLS, "invalid execution ordinal")
        check(CALL_ORDER[self.ordinal - 1] == (self.task_id, self.condition), "order mismatch")


@dataclass(frozen=True)
class ExecutionResult:
    identity: ExecutionIdentity
    status: ExecutionStatus
    accepted_provider_call_count: int
    input_tokens: int
    output_tokens: int
    observed_cost_usd: Decimal
    reserved_cost_usd: Decimal
    patch_extraction: StageStatus
    validation: StageStatus
    sandbox_evaluation: StageStatus
    architecture_evaluation: StageStatus
    terminal_classification: TerminalClassification
    diagnostic_fingerprints: tuple[str, ...] = ()
    response_state: ProviderResponseState = ProviderResponseState.COMPLETED

    def __post_init__(self) -> None:
        check(
            self.accepted_provider_call_count == 1, "scientific result requires one accepted call"
        )
        SyntheticUsage(self.input_tokens, self.output_tokens)
        check(self.observed_cost_usd >= 0, "negative observed cost")
        check(self.reserved_cost_usd in {Decimal("0"), PER_CALL_RESERVATION}, "bad reservation")
        values = tuple(self.diagnostic_fingerprints)
        check(values == tuple(sorted(set(values))), "diagnostics must be unique and sorted")
        for value in values:
            digest(value)
        check(
            self.response_state == ProviderResponseState.COMPLETED,
            "scientific completion requires a completed provider response",
        )
        object.__setattr__(self, "diagnostic_fingerprints", values)


@dataclass(frozen=True)
class ProviderFailureDiagnostic:
    kind: ProviderFailureKind
    stage: str
    retryable: bool
    http_status: int | None
    provider_code: str | None
    usage_returned: bool
    request_id_hash: str | None
    fingerprint: str = ""

    def __post_init__(self) -> None:
        import hashlib
        import re
        from dataclasses import asdict

        from archguard.domain.canonical import canonical_json

        check(re.fullmatch(r"[a-z_]{1,64}", self.stage) is not None, "invalid failure stage")
        check(self.http_status is None or 100 <= self.http_status <= 599, "invalid HTTP status")
        check(
            self.provider_code is None
            or re.fullmatch(r"[a-z0-9_.-]{1,64}", self.provider_code) is not None,
            "unsafe provider code",
        )
        if self.request_id_hash is not None:
            digest(self.request_id_hash)
        payload = {key: value for key, value in asdict(self).items() if key != "fingerprint"}
        expected = hashlib.sha256(canonical_json(payload)).hexdigest()
        check(not self.fingerprint or self.fingerprint == expected, "failure fingerprint mismatch")
        object.__setattr__(self, "fingerprint", expected)


@dataclass(frozen=True)
class ProviderFailureRecord:
    identity: ExecutionIdentity
    diagnostic: ProviderFailureDiagnostic
    accepted_provider_call_count: int
    input_tokens: int
    output_tokens: int
    observed_cost_usd: Decimal
    response_state: ProviderResponseState = ProviderResponseState.NOT_RECEIVED

    def __post_init__(self) -> None:
        check(self.accepted_provider_call_count in {0, 1}, "invalid accepted call count")
        usage = SyntheticUsage(self.input_tokens, self.output_tokens)
        check(self.observed_cost_usd == usage.cost, "failure cost mismatch")
        if self.accepted_provider_call_count == 0:
            check(
                usage == SyntheticUsage(0, 0) and self.observed_cost_usd == 0,
                "uncharged failure contains usage or cost",
            )
            check(
                self.response_state == ProviderResponseState.NOT_RECEIVED,
                "unaccepted failure cannot contain response state",
            )
        else:
            check(
                self.diagnostic.usage_returned,
                "accepted failure requires trustworthy returned usage",
            )
            check(
                self.response_state != ProviderResponseState.NOT_RECEIVED,
                "accepted failure requires response state",
            )


@dataclass(frozen=True)
class BudgetLedger:
    completed_ordinals: tuple[int, ...] = ()
    failed_attempt_ordinals: tuple[int, ...] = ()
    provider_request_attempts: int = 0
    accepted_provider_calls: int = 0
    infrastructure_failures: int = 0
    in_flight_ordinal: int | None = None
    observed_cost_usd: Decimal = Decimal("0")
    reserved_cost_usd: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        completed = tuple(self.completed_ordinals)
        failed = tuple(self.failed_attempt_ordinals)
        check(completed == tuple(sorted(set(completed))), "duplicate or unordered ordinals")
        check(failed == tuple(sorted(set(failed))), "duplicate or unordered failed ordinals")
        check(all(1 <= item <= MAX_CALLS for item in completed), "invalid completed ordinal")
        check(completed == tuple(range(1, len(completed) + 1)), "contradictory resume state")
        check(not set(completed) & set(failed), "completed and failed ordinals overlap")
        check(
            failed in {(), (len(completed) + 1,)},
            "failed ordinal must be the next scientific execution",
        )
        check(
            self.provider_request_attempts == len(completed) + len(failed),
            "provider attempt count contradicts ordinal state",
        )
        check(
            len(completed) <= self.accepted_provider_calls <= self.provider_request_attempts,
            "accepted provider call count is contradictory",
        )
        check(
            self.infrastructure_failures == len(failed),
            "infrastructure failure count is contradictory",
        )
        check(self.provider_request_attempts <= MAX_CALLS, "provider request ceiling exceeded")
        check(self.observed_cost_usd >= 0, "negative observed cost")
        check(self.observed_cost_usd <= HARD_CEILING, "observed cost exceeds ceiling")
        if self.in_flight_ordinal is None:
            check(self.reserved_cost_usd == 0, "reservation without in-flight call")
        else:
            check(not failed, "failed run cannot retain an in-flight reservation")
            check(self.in_flight_ordinal == len(completed) + 1, "contradictory in-flight ordinal")
            check(self.reserved_cost_usd == PER_CALL_RESERVATION, "invalid reservation")

    @property
    def completed_calls(self) -> int:
        return len(self.completed_ordinals)

    @property
    def remaining_calls(self) -> int:
        return MAX_CALLS - self.completed_calls

    @property
    def remaining_provider_requests(self) -> int:
        return MAX_CALLS - self.provider_request_attempts

    def reserve(self, ordinal: int) -> BudgetLedger:
        check(self.in_flight_ordinal is None, "ambiguous in-flight reservation")
        check(not self.failed_attempt_ordinals, "failed ordinal requires protocol amendment")
        check(ordinal == self.completed_calls + 1, "out-of-order or duplicate ordinal")
        check(self.provider_request_attempts < MAX_CALLS, "provider call ceiling reached")
        check(PER_CALL_RESERVATION <= Decimal("0.1175"), "per-call ceiling exceeded")
        check(
            Decimal(self.provider_request_attempts + 1) * PER_CALL_RESERVATION <= TOTAL_RESERVATION,
            "total reservation ceiling exceeded",
        )
        check(
            self.observed_cost_usd + PER_CALL_RESERVATION <= HARD_CEILING,
            "absolute cost ceiling would be exceeded",
        )
        return replace(self, in_flight_ordinal=ordinal, reserved_cost_usd=PER_CALL_RESERVATION)

    def reconcile_success(self, ordinal: int, usage: SyntheticUsage) -> BudgetLedger:
        check(self.in_flight_ordinal == ordinal, "missing or contradictory reservation")
        check(usage.cost <= self.reserved_cost_usd, "usage contradicts reservation")
        return BudgetLedger(
            completed_ordinals=(*self.completed_ordinals, ordinal),
            provider_request_attempts=self.provider_request_attempts + 1,
            accepted_provider_calls=self.accepted_provider_calls + 1,
            observed_cost_usd=self.observed_cost_usd + usage.cost,
        )

    def record_provider_failure(self, ordinal: int, usage: SyntheticUsage | None) -> BudgetLedger:
        check(self.in_flight_ordinal == ordinal, "missing or contradictory reservation")
        accepted = int(usage is not None)
        observed = Decimal("0") if usage is None else usage.cost
        check(observed <= self.reserved_cost_usd, "failure usage contradicts reservation")
        if usage is not None:
            check(usage.cost > 0, "zero-usage failure is not a charged provider call")
        return BudgetLedger(
            completed_ordinals=self.completed_ordinals,
            failed_attempt_ordinals=(ordinal,),
            provider_request_attempts=self.provider_request_attempts + 1,
            accepted_provider_calls=self.accepted_provider_calls + accepted,
            infrastructure_failures=self.infrastructure_failures + 1,
            observed_cost_usd=self.observed_cost_usd + observed,
        )

    def cancel_pre_provider(self, ordinal: int) -> BudgetLedger:
        check(self.in_flight_ordinal == ordinal, "missing reservation")
        return replace(self, in_flight_ordinal=None, reserved_cost_usd=Decimal("0"))


def frozen_identities() -> tuple[ExecutionIdentity, ...]:
    return tuple(ExecutionIdentity(index, *pair) for index, pair in enumerate(CALL_ORDER, 1))
