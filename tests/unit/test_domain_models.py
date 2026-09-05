from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import TypeAdapter

from archguard.domain.enums import ArtifactKind, Severity
from archguard.domain.models import (
    ArchitectureViolation,
    ArtifactReference,
    ExecutionResult,
    ExperimentIdentity,
    ValidationSummary,
    relative_path,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "path",
    [
        "../x",
        "/tmp/x",
        "x/../y",
        "C:/x",
        "C:x",
        "\\server\\x",
        "x\\..\\y",
        "",
        " ",
        ".",
        "x\\y",
        "./",
        "a\x00b",
    ],
)
def test_unsafe_paths(path: str) -> None:
    with pytest.raises(ValueError):
        relative_path(path)


@pytest.mark.parametrize("path", ["results/a.json", "a", "nested/./a"])
def test_safe_paths(path: str) -> None:
    assert not relative_path(path).startswith("/")


def test_identity_utc_immutable_and_serialization() -> None:
    identity = ExperimentIdentity(
        "exp", "run", datetime(2025, 1, 1, tzinfo=timezone(timedelta(hours=3)))
    )
    assert identity.created_at.tzinfo is UTC
    assert identity.created_at.hour == 21
    with pytest.raises(FrozenInstanceError):
        identity.run_id = "changed"  # type: ignore[misc]  # Exercise frozen runtime guard.
    adapter = TypeAdapter(ExperimentIdentity)
    assert adapter.dump_json(identity) == adapter.dump_json(identity)
    assert adapter.validate_json(adapter.dump_json(identity)) == identity


@pytest.mark.parametrize(
    "experiment,run,stamp",
    [
        ("", "r", datetime(2025, 1, 1, tzinfo=UTC)),
        ("e", " ", datetime(2025, 1, 1, tzinfo=UTC)),
        ("e", "r", datetime(2025, 1, 1)),
    ],
)
def test_invalid_identity(experiment: str, run: str, stamp: datetime) -> None:
    with pytest.raises(ValueError):
        ExperimentIdentity(experiment, run, stamp)


@pytest.mark.parametrize("duration", [-1, float("inf"), float("nan")])
def test_invalid_duration(duration: float) -> None:
    with pytest.raises(ValueError):
        ExecutionResult("", "", 0, duration)


def test_execution_contract() -> None:
    assert ExecutionResult("out", "err", None, 1, True).timed_out
    with pytest.raises(ValueError):
        ExecutionResult("", "", None, 0)


def test_artifact_and_validation() -> None:
    assert ArtifactReference("a/./b", ArtifactKind.LOG).path == "a/b"
    assert ValidationSummary().passed
    warning = ArchitectureViolation("rule", "message", Severity.WARNING)
    assert ValidationSummary((warning,)).passed
    assert not ValidationSummary((ArchitectureViolation("r", "m", Severity.ERROR),)).passed
    with pytest.raises(ValueError):
        ArchitectureViolation("", "message", Severity.INFO)
