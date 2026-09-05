import re
from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite
from pathlib import PurePosixPath, PureWindowsPath

from archguard.domain.enums import ArtifactKind, Severity
from archguard.domain.errors import DomainValidationError


def identifier(value: str) -> str:
    if not value.strip():
        raise DomainValidationError("identifier must not be empty")
    return value


def relative_path(value: str) -> str:
    identifier(value)
    posix, windows = PurePosixPath(value), PureWindowsPath(value)
    if posix.is_absolute() or windows.anchor or ".." in windows.parts or ".." in posix.parts:
        raise DomainValidationError("artifact path must be relative without parent traversal")
    if "\\" in value or posix.as_posix() == "." or "\x00" in value:
        raise DomainValidationError("artifact path must use POSIX separators and name an artifact")
    return posix.as_posix()


@dataclass(frozen=True)
class ExperimentIdentity:
    experiment_id: str
    run_id: str
    created_at: datetime

    def __post_init__(self) -> None:
        identifier(self.experiment_id)
        identifier(self.run_id)
        if self.created_at.utcoffset() is None:
            raise DomainValidationError("timestamp must be timezone-aware")
        object.__setattr__(self, "created_at", self.created_at.astimezone(UTC))


@dataclass(frozen=True)
class ArtifactReference:
    path: str
    kind: ArtifactKind
    sha256: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", relative_path(self.path))
        if self.sha256 is not None:
            if re.fullmatch(r"[0-9a-f]{64}", self.sha256) is None:
                raise DomainValidationError("invalid artifact SHA-256")
        if not isinstance(self.kind, ArtifactKind):
            raise DomainValidationError("invalid artifact kind")


@dataclass(frozen=True)
class ExecutionResult:
    stdout: str
    stderr: str
    exit_code: int | None
    duration_seconds: float
    timed_out: bool = False

    def __post_init__(self) -> None:
        if not isfinite(self.duration_seconds) or self.duration_seconds < 0:
            raise DomainValidationError("duration must be finite and non-negative")
        if self.exit_code is None and not self.timed_out:
            raise DomainValidationError("completed execution requires an exit code")


@dataclass(frozen=True)
class ArchitectureViolation:
    rule_id: str
    message: str
    severity: Severity

    def __post_init__(self) -> None:
        identifier(self.rule_id)
        identifier(self.message)
        if not isinstance(self.severity, Severity):
            raise DomainValidationError("invalid severity")


@dataclass(frozen=True)
class ValidationSummary:
    violations: tuple[ArchitectureViolation, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "violations", tuple(self.violations))

    @property
    def passed(self) -> bool:
        return not any(item.severity == Severity.ERROR for item in self.violations)
