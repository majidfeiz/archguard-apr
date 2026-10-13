import hashlib
import io
import json
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from archguard.application.services.phase13 import (
    _checkpoint_results,
    _register_call,
    run_frozen_experiment,
)
from archguard.domain.canonical import canonical_json
from archguard.domain.orchestration import fingerprint
from archguard.domain.phase13 import CostState
from archguard.entrypoints.cli.app import app
from archguard.infrastructure.phase13_artifacts import SourceFreeArtifacts
from archguard.infrastructure.phase13_checkpoint import (
    ARCHIVE_SHA256,
    INCIDENT_FINGERPRINT,
    import_checkpoint,
    load_checkpoint,
)
from archguard.infrastructure.provider_preflight import load_phase13_provider_configuration
from tests.unit.test_phase13_runner import FakeExecutor

CHECKPOINT = Path("research/evidence/phase-13-checkpoint-run-38452767198.json")
PROTOCOL = "eae1920ce71c025d2d94096798daf8b14df098249743631efe9a0aa7a541fbe8"


def test_committed_checkpoint_is_canonical_and_exact(repository_root: Path) -> None:
    value = load_checkpoint(repository_root / CHECKPOINT)
    assert value["completed_ordinals"] == [1]
    assert value["next_ordinal"] == 2
    assert value["remaining_ordinals"] == [2, 3, 4, 5, 6]
    assert value["carried_observed_usd"] == "0.025945"
    assert value["carried_provider_calls"] == 1


def test_archive_import_is_deterministic_and_idempotent(repository_root: Path) -> None:
    archive = Path("/tmp/phase-13-provider-preflight-11840547579.zip")
    if not archive.exists():
        pytest.skip("reviewed incident archive is not present")
    first = import_checkpoint(archive, INCIDENT_FINGERPRINT)
    second = import_checkpoint(archive, INCIDENT_FINGERPRINT)
    assert first == second == load_checkpoint(repository_root / CHECKPOINT)
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == ARCHIVE_SHA256


def test_archive_hash_mismatch_fails_before_parsing(tmp_path: Path) -> None:
    archive = tmp_path / "wrong.zip"
    archive.write_bytes(b"not the reviewed archive")
    with pytest.raises(ValueError, match="identity mismatch"):
        import_checkpoint(archive, INCIDENT_FINGERPRINT)


def test_malicious_archive_member_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "malicious.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../source.py", "secret")
    monkeypatch.setattr(
        "archguard.infrastructure.phase13_checkpoint.ARCHIVE_SHA256",
        hashlib.sha256(archive.read_bytes()).hexdigest(),
    )
    with pytest.raises(ValueError, match="members mismatch"):
        import_checkpoint(archive, INCIDENT_FINGERPRINT)


def test_traversal_is_rejected_after_archive_identity_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "traversal.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../source.json", "{}")
    monkeypatch.setattr(
        "archguard.infrastructure.phase13_checkpoint.ARCHIVE_SHA256",
        hashlib.sha256(archive.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(
        "archguard.infrastructure.phase13_checkpoint.MEMBERS", frozenset({"../source.json"})
    )
    with pytest.raises(ValueError, match="unsafe"):
        import_checkpoint(archive, INCIDENT_FINGERPRINT)


def test_oversized_member_is_rejected_after_archive_identity_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "large.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("large.json", " " * 5000)
    monkeypatch.setattr(
        "archguard.infrastructure.phase13_checkpoint.ARCHIVE_SHA256",
        hashlib.sha256(archive.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(
        "archguard.infrastructure.phase13_checkpoint.MEMBERS", frozenset({"large.json"})
    )
    with pytest.raises(ValueError, match="too large"):
        import_checkpoint(archive, INCIDENT_FINGERPRINT)


def test_non_object_json_member_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "array.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("one.json", "[]")
    monkeypatch.setattr(
        "archguard.infrastructure.phase13_checkpoint.ARCHIVE_SHA256",
        hashlib.sha256(archive.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(
        "archguard.infrastructure.phase13_checkpoint.MEMBERS", frozenset({"one.json"})
    )
    with pytest.raises(ValueError, match="JSON object"):
        import_checkpoint(archive, INCIDENT_FINGERPRINT)


def test_duplicate_archive_members_are_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "duplicate.zip"
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as bundle:
        bundle.writestr("same.json", "{}")
        with pytest.warns(UserWarning):
            bundle.writestr("same.json", "{}")
    archive.write_bytes(stream.getvalue())
    monkeypatch.setattr(
        "archguard.infrastructure.phase13_checkpoint.ARCHIVE_SHA256",
        hashlib.sha256(archive.read_bytes()).hexdigest(),
    )
    with pytest.raises(ValueError, match="members mismatch"):
        import_checkpoint(archive, INCIDENT_FINGERPRINT)


def test_resume_starts_at_two_and_preserves_carried_evidence(
    repository_root: Path, tmp_path: Path
) -> None:
    checkpoint = load_checkpoint(repository_root / CHECKPOINT)
    configuration = load_phase13_provider_configuration(
        repository_root / "configs/experiments/phase13-provider.json"
    )
    executor = FakeExecutor(PROTOCOL)
    output = tmp_path / "evidence"
    results = run_frozen_experiment(
        protocol_fingerprint=PROTOCOL,
        configuration=configuration,
        executor=executor,
        artifacts=SourceFreeArtifacts(output),
        checkpoint=checkpoint,
    )
    assert [request.identity.ordinal for request in executor.requests] == [2, 3, 4, 5, 6]
    assert [result.identity.ordinal for result in results] == [1, 2, 3, 4, 5, 6]
    imported = json.loads((output / "execution-1.json").read_text())
    assert imported == checkpoint["completed_executions"][0]
    state = json.loads((output / "cost-state.json").read_text())
    assert state["provider_calls_started"] == 6
    assert state["observed_usd"] == "0.026945"
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["carried_executions"] == 1
    assert manifest["newly_completed_executions"] == 5
    assert manifest["carried_provider_calls"] == 1
    assert manifest["new_provider_calls"] == 5


@pytest.mark.parametrize(
    "field,value",
    [
        ("completed_ordinals", [1, 3]),
        ("completed_ordinals", [2]),
        ("remaining_ordinals", [3, 2, 4, 5, 6]),
    ],
)
def test_corrupted_checkpoint_fails_closed(
    repository_root: Path, tmp_path: Path, field: str, value: object
) -> None:
    checkpoint = load_checkpoint(repository_root / CHECKPOINT)
    checkpoint[field] = value
    target = tmp_path / "checkpoint.json"
    target.write_text(json.dumps(checkpoint, sort_keys=True, separators=(",", ":")) + "\n")
    with pytest.raises(ValueError):
        load_checkpoint(target)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.update(schema="wrong"), "invariant"),
        (lambda value: value.update(completed_executions=[]), "executions"),
        (lambda value: value.update(call_ledger=[]), "call ledger"),
        (lambda value: value.update(call_ledger=[{"ordinal": 1}]), "call identity"),
        (lambda value: value.update(completed_executions=["bad"]), "execution"),
        (
            lambda value: value["completed_executions"][0].update(task_id="substitute"),
            "execution mismatch",
        ),
    ],
)
def test_canonically_rehashed_contradictions_are_rejected(
    repository_root: Path,
    tmp_path: Path,
    mutation: Callable[[dict[str, Any]], None],
    message: str,
) -> None:
    value = load_checkpoint(repository_root / CHECKPOINT)
    mutation(value)
    value["checkpoint_fingerprint"] = fingerprint(
        {key: item for key, item in value.items() if key != "checkpoint_fingerprint"}
    )
    target = tmp_path / "contradiction.json"
    target.write_bytes(canonical_json(value))
    with pytest.raises(ValueError, match=message):
        load_checkpoint(target)


def test_dry_run_checkpoint_validation_has_no_provider_call(repository_root: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "experiment",
            "validate-checkpoint",
            "--checkpoint",
            str(repository_root / CHECKPOINT),
        ],
    )
    assert result.exit_code == 0
    value = json.loads(result.stdout)
    assert value["network_request"] is False
    assert value["next_ordinal"] == 2
    assert value["carried_provider_calls"] == 1


def test_resume_helpers_reject_duplicate_calls_and_non_prefixes(repository_root: Path) -> None:
    checkpoint = load_checkpoint(repository_root / CHECKPOINT)
    with pytest.raises(ValueError, match="protocol drift"):
        _checkpoint_results(checkpoint, "0" * 64)
    checkpoint["completed_ordinals"] = [2]
    with pytest.raises(ValueError, match="exact prefix"):
        _checkpoint_results(checkpoint, PROTOCOL)
    state = CostState(
        provider_calls_started=1,
        provider_calls_completed=1,
        provider_calls_with_usage=1,
        call_ids=("a" * 64,),
    )
    with pytest.raises(ValueError, match="duplicate"):
        _register_call(state, "a" * 64, completed=True, usage=True)
