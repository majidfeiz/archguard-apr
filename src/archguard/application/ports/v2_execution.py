"""Ports for V2.2 provider calls, candidate handling and source-free checkpoints."""

from dataclasses import dataclass
from typing import Protocol

from archguard.domain.v2_execution import (
    BudgetLedger,
    ExecutionIdentity,
    ExecutionResult,
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


@dataclass(frozen=True)
class CandidateAssessment:
    patch_extraction: StageStatus
    validation: StageStatus
    sandbox_evaluation: StageStatus
    architecture_evaluation: StageStatus
    classification: TerminalClassification
    diagnostic_fingerprints: tuple[str, ...] = ()


class ProviderChargedFailure(RuntimeError):
    def __init__(self, usage: SyntheticUsage, diagnostic_fingerprint: str) -> None:
        super().__init__("provider call failed after usage was charged")
        self.usage = usage
        self.diagnostic_fingerprint = diagnostic_fingerprint


class RequestPreparer(Protocol):
    def prepare(self, identity: ExecutionIdentity) -> PreparedRequest: ...


class Provider(Protocol):
    def invoke(self, request: PreparedRequest) -> ProviderOutcome: ...


class CandidateProcessor(Protocol):
    def process(self, request: PreparedRequest, response: bytes) -> CandidateAssessment: ...


class CheckpointStore(Protocol):
    def write(self, ledger: BudgetLedger, results: tuple[ExecutionResult, ...]) -> None: ...


class Cleanup(Protocol):
    def cleanup(self) -> bool: ...
