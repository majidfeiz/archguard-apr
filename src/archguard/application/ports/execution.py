from pathlib import Path
from typing import Protocol

from archguard.domain.models import ExecutionResult


class ExecutionRunnerPort(Protocol):
    def run(
        self, command: tuple[str, ...], workspace: Path, timeout_seconds: float
    ) -> ExecutionResult:
        """Execute in isolation; reject empty commands and non-positive/non-finite timeouts.

        Implementations must enforce isolation and return captured streams and timeout state.
        """
        ...
