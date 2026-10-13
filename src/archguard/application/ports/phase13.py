"""Ports for the frozen experiment; source-bearing values never cross persistence."""

from dataclasses import dataclass
from typing import Protocol

from archguard.domain.phase13 import ExecutionIdentity, ExecutionResult, ProviderUsage


@dataclass(frozen=True)
class TreatmentRequest:
    identity: ExecutionIdentity
    request_fingerprint: str
    context_manifest_fingerprint: str
    architecture_treatment: bool
    provider_call_id: str = ""


@dataclass(frozen=True)
class CandidateResponse:
    response_fingerprint: str
    patch_fingerprint: str
    usage: ProviderUsage


class ProviderAttemptError(RuntimeError):
    def __init__(self, category: str) -> None:
        super().__init__(category)
        self.category = category


class FrozenExecutionPort(Protocol):
    """Own acquisition, provider invocation, patch validation, evaluation and cleanup."""

    def execute(self, request: TreatmentRequest, *, retry: bool = False) -> ExecutionResult: ...

    def cleanup(self) -> bool: ...


class Phase13ArtifactPort(Protocol):
    def write_cost_state(self, value: object) -> None: ...

    def write_result(self, result: ExecutionResult) -> None: ...

    def write_imported_result(self, ordinal: int, value: object) -> None: ...

    def write_manifest(self, value: object) -> None: ...

    def write_cleanup(self, value: object) -> None: ...
