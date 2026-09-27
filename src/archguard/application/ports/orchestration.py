"""Narrow provider-neutral orchestration ports."""

from pathlib import Path
from typing import Protocol

from archguard.domain.orchestration import (
    AgentRequest,
    AgentResponse,
    RepairCheckpoint,
    RepairRunSpec,
    RunEvent,
)


class AgentPort(Protocol):
    def invoke(self, request: AgentRequest) -> AgentResponse: ...


class RunSpecPort(Protocol):
    def load(self, source: Path) -> RepairRunSpec: ...


class RunArtifactPort(Protocol):
    def write_run(
        self,
        directory: Path,
        spec: RepairRunSpec,
        events: tuple[RunEvent, ...],
        checkpoint: RepairCheckpoint,
    ) -> None: ...

    def read_run(
        self, directory: Path
    ) -> tuple[RepairRunSpec, tuple[RunEvent, ...], RepairCheckpoint]: ...
