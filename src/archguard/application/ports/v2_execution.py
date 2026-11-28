"""Ports for V2.2 provider calls, candidate handling and source-free checkpoints."""

from dataclasses import dataclass
from typing import Protocol

from archguard.domain.providers import ProviderResponseState
from archguard.domain.v2_execution import (
    BudgetLedger,
    ExecutionIdentity,
    ExecutionResult,
    ProviderFailureDiagnostic,
    ProviderFailureRecord,
    StageStatus,
    TerminalClassification,
)
from archguard.domain.v2_micro_pilot import SyntheticUsage


@dataclass(frozen=True)
class PreparedRequest:
    identity: ExecutionIdentity
    prompt: str
    fairness_fingerprint: str


@dataclass(frozen=True)
class ProviderOutcome:
    response: bytes
    usage: SyntheticUsage
    response_state: ProviderResponseState = ProviderResponseState.COMPLETED


@dataclass(frozen=True)
class CandidateAssessment:
    patch_extraction: StageStatus
    validation: StageStatus
    sandbox_evaluation: StageStatus
    architecture_evaluation: StageStatus
    classification: TerminalClassification
    diagnostic_fingerprints: tuple[str, ...] = ()


class ProviderChargedFailure(RuntimeError):
    def __init__(
        self,
        usage: SyntheticUsage,
        diagnostic: ProviderFailureDiagnostic,
        response_state: ProviderResponseState,
    ) -> None:
        if usage.cost <= 0:
            raise ValueError("charged provider failure requires positive trustworthy usage")
        super().__init__("provider call failed after usage was charged")
        self.usage = usage
        self.diagnostic = diagnostic
        self.response_state = response_state


class ProviderAdmissionFailure(RuntimeError):
    def __init__(self, diagnostic: ProviderFailureDiagnostic) -> None:
        super().__init__("provider request was rejected without trustworthy usage")
        self.diagnostic = diagnostic


class RequestPreparer(Protocol):
    def prepare(self, identity: ExecutionIdentity) -> PreparedRequest: ...


class Provider(Protocol):
    def invoke(self, request: PreparedRequest) -> ProviderOutcome: ...


class CandidateProcessor(Protocol):
    def process(self, request: PreparedRequest, response: bytes) -> CandidateAssessment: ...


class CheckpointStore(Protocol):
    def write(
        self,
        ledger: BudgetLedger,
        results: tuple[ExecutionResult, ...],
        failures: tuple[ProviderFailureRecord, ...],
    ) -> None: ...


class Cleanup(Protocol):
    def cleanup(self) -> bool: ...
