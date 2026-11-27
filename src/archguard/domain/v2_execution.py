"""Frozen, provider-neutral contracts for the bounded V2.2 micro-pilot."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from enum import StrEnum

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
    provider_call_count: int
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

    def __post_init__(self) -> None:
        check(self.provider_call_count in {0, 1}, "invalid provider call count")
        SyntheticUsage(self.input_tokens, self.output_tokens)
        check(self.observed_cost_usd >= 0, "negative observed cost")
        check(self.reserved_cost_usd in {Decimal("0"), PER_CALL_RESERVATION}, "bad reservation")
        values = tuple(self.diagnostic_fingerprints)
        check(values == tuple(sorted(set(values))), "diagnostics must be unique and sorted")
        for value in values:
            digest(value)
        object.__setattr__(self, "diagnostic_fingerprints", values)


@dataclass(frozen=True)
class BudgetLedger:
    completed_ordinals: tuple[int, ...] = ()
    in_flight_ordinal: int | None = None
    observed_cost_usd: Decimal = Decimal("0")
    reserved_cost_usd: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        completed = tuple(self.completed_ordinals)
        check(completed == tuple(sorted(set(completed))), "duplicate or unordered ordinals")
        check(all(1 <= item <= MAX_CALLS for item in completed), "invalid completed ordinal")
        check(completed == tuple(range(1, len(completed) + 1)), "contradictory resume state")
        check(self.observed_cost_usd >= 0, "negative observed cost")
        check(self.observed_cost_usd <= HARD_CEILING, "observed cost exceeds ceiling")
        if self.in_flight_ordinal is None:
            check(self.reserved_cost_usd == 0, "reservation without in-flight call")
        else:
            check(self.in_flight_ordinal == len(completed) + 1, "contradictory in-flight ordinal")
            check(self.reserved_cost_usd == PER_CALL_RESERVATION, "invalid reservation")

    @property
    def completed_calls(self) -> int:
        return len(self.completed_ordinals)

    @property
    def remaining_calls(self) -> int:
        return MAX_CALLS - self.completed_calls

    def reserve(self, ordinal: int) -> BudgetLedger:
        check(self.in_flight_ordinal is None, "ambiguous in-flight reservation")
        check(ordinal == self.completed_calls + 1, "out-of-order or duplicate ordinal")
        check(ordinal <= MAX_CALLS, "provider call ceiling reached")
        check(PER_CALL_RESERVATION <= Decimal("0.1175"), "per-call ceiling exceeded")
        check(
            Decimal(self.completed_calls + 1) * PER_CALL_RESERVATION <= TOTAL_RESERVATION,
            "total reservation ceiling exceeded",
        )
        check(
            self.observed_cost_usd + PER_CALL_RESERVATION <= HARD_CEILING,
            "absolute cost ceiling would be exceeded",
        )
        return replace(self, in_flight_ordinal=ordinal, reserved_cost_usd=PER_CALL_RESERVATION)

    def reconcile(self, ordinal: int, usage: SyntheticUsage) -> BudgetLedger:
        check(self.in_flight_ordinal == ordinal, "missing or contradictory reservation")
        check(usage.cost <= self.reserved_cost_usd, "usage contradicts reservation")
        return BudgetLedger(
            (*self.completed_ordinals, ordinal), None, self.observed_cost_usd + usage.cost
        )

    def cancel_pre_provider(self, ordinal: int) -> BudgetLedger:
        check(self.in_flight_ordinal == ordinal, "missing reservation")
        return BudgetLedger(self.completed_ordinals, None, self.observed_cost_usd)


def frozen_identities() -> tuple[ExecutionIdentity, ...]:
    return tuple(ExecutionIdentity(index, *pair) for index, pair in enumerate(CALL_ORDER, 1))
