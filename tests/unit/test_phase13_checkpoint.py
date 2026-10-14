import hashlib
import io
import json
import zipfile
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from archguard.application.services.phase13 import (
    ControlledStop,
    _checkpoint_results,
    _register_call,
    run_frozen_experiment,
)
from archguard.domain.canonical import canonical_json
from archguard.domain.orchestration import fingerprint
from archguard.domain.phase13 import (
    CostState,
    ResumeStopClassification,
    ResumeStopReason,
    classify_resume_stop,
)
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

CHECKPOINT = Path("research/evidence/phase-13-checkpoint-four-executions.json")
PROTOCOL = "eae1920ce71c025d2d94096798daf8b14df098249743631efe9a0aa7a541fbe8"


def test_committed_checkpoint_is_canonical_and_exact(repository_root: Path) -> None:
    value = load_checkpoint(repository_root / CHECKPOINT)
    assert value["completed_ordinals"] == [1, 2, 3, 4]
    assert value["next_ordinal"] == 5
    assert value["remaining_ordinals"] == [5, 6]
    assert value["carried_observed_usd"] == "0.1296325"
    assert value["carried_provider_calls"] == 4
    assert value["historical_stop_reason"] == "pre_provider_failure"
    assert value["active_stop_reason"] is None
    assert value["resume_allowed"] is True


def test_archive_import_is_deterministic_and_idempotent(repository_root: Path) -> None:
    archive = Path("/tmp/phase-13-provider-preflight-four-executions.zip")
    if not archive.exists():
        pytest.skip("reviewed incident archive is not present")
    first = import_checkpoint(archive, INCIDENT_FINGERPRINT)
    second = import_checkpoint(archive, INCIDENT_FINGERPRINT)
    assert first == second == load_checkpoint(repository_root / CHECKPOINT)
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == ARCHIVE_SHA256


def test_four_execution_archive_import_matches_committed_checkpoint(
    repository_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkpoint = load_checkpoint(repository_root / CHECKPOINT)
    call_ids = [item["call_id"] for item in checkpoint["call_ledger"]]
    result_fingerprints = [
        hashlib.sha256(canonical_json(item)).hexdigest()
        for item in checkpoint["completed_executions"]
    ]
    members: dict[str, object] = {
        "home/runner/work/_temp/provider-preflight.json": {
            "schema": "archguard.provider-preflight/v1",
            "network_request": False,
        },
        "home/runner/work/_temp/checkpoint.json": {},
        "tmp/archguard-phase13-cost-state.json": {
            "completed_primary_executions": 0,
            "observed_provider_cost_usd": "0",
        },
        "tmp/archguard-phase13-evidence/cleanup.json": {
            "complete": True,
            "schema": "archguard.phase-13-cleanup/v1",
        },
        "tmp/archguard-phase13-evidence/cost-state.json": {
            "schema": "archguard.phase-13-cost-state/v1",
            "completed_primary": 4,
            "provider_calls_started": 4,
            "provider_calls_completed": 4,
            "provider_calls_with_usage": 4,
            "observed_usd": "0.1296325",
            "call_ids": call_ids,
        },
        "tmp/archguard-phase13-evidence/manifest.json": {
            "schema": "archguard.phase-13-manifest/v1",
            "completed_executions": 4,
            "provider_calls_completed": 4,
            "total_cost_usd": "0.1296325",
            "result_fingerprints": result_fingerprints,
        },
        "tmp/archguard-phase13-evidence/pre-provider-failure.json": checkpoint[
            "historical_pre_provider_failure"
        ],
    }
    for ordinal, execution in enumerate(checkpoint["completed_executions"], start=1):
        members[f"tmp/archguard-phase13-evidence/execution-{ordinal}.json"] = execution
    archive = tmp_path / "reviewed.zip"

    def write_archive() -> None:
        with zipfile.ZipFile(archive, "w") as bundle:
            for name, value in members.items():
                bundle.writestr(name, canonical_json(value))

    write_archive()
    monkeypatch.setattr(
        "archguard.infrastructure.phase13_checkpoint.ARCHIVE_SHA256",
        hashlib.sha256(archive.read_bytes()).hexdigest(),
    )
    imported = import_checkpoint(archive, INCIDENT_FINGERPRINT)
    imported["archive_sha256"] = checkpoint["archive_sha256"]
    imported["checkpoint_fingerprint"] = checkpoint["checkpoint_fingerprint"]
    assert imported == checkpoint
    members["home/runner/work/_temp/provider-preflight.json"] = {
        "schema": "archguard.provider-preflight/v1",
        "network_request": True,
    }
    write_archive()
    monkeypatch.setattr(
        "archguard.infrastructure.phase13_checkpoint.ARCHIVE_SHA256",
        hashlib.sha256(archive.read_bytes()).hexdigest(),
    )
    with pytest.raises(ValueError, match="preflight"):
        import_checkpoint(archive, INCIDENT_FINGERPRINT)


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


def test_resume_starts_at_five_and_preserves_carried_evidence(
    repository_root: Path, tmp_path: Path
) -> None:
    checkpoint = load_checkpoint(repository_root / CHECKPOINT)
    carried_evidence = [canonical_json(item) for item in checkpoint["completed_executions"]]
    configuration = load_phase13_provider_configuration(
        repository_root / "configs/experiments/phase13-provider.json"
    )
    executor = FakeExecutor(PROTOCOL)
    output = tmp_path / "evidence"

    class RecordingArtifacts(SourceFreeArtifacts):
        states: list[dict[str, Any]] = []

        def write_cost_state(self, value: object) -> None:
            assert isinstance(value, dict)
            self.states.append(value.copy())
            super().write_cost_state(value)

    artifacts = RecordingArtifacts(output)
    results = run_frozen_experiment(
        protocol_fingerprint=PROTOCOL,
        configuration=configuration,
        executor=executor,
        artifacts=artifacts,
        checkpoint=checkpoint,
    )
    assert artifacts.states[0] == {
        "observed_usd": Decimal("0.1296325"),
        "reserved_usd": Decimal("0"),
        "completed_primary": 4,
        "attempted_retries": 0,
        "provider_calls_started": 4,
        "provider_calls_completed": 4,
        "provider_calls_with_usage": 4,
        "call_ids": tuple(item["call_id"] for item in checkpoint["call_ledger"]),
        "stop_reason": None,
    }
    assert [request.identity.ordinal for request in executor.requests] == [5, 6]
    assert [result.identity.ordinal for result in results] == [1, 2, 3, 4, 5, 6]
    imported = [json.loads((output / f"execution-{n}.json").read_text()) for n in range(1, 5)]
    assert imported == checkpoint["completed_executions"]
    assert [canonical_json(item) for item in imported] == carried_evidence
    state = json.loads((output / "cost-state.json").read_text())
    assert state["provider_calls_started"] == 6
    assert state["provider_calls_completed"] == 6
    assert state["provider_calls_with_usage"] == 6
    assert state["observed_usd"] == "0.1300325"
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["carried_executions"] == 4
    assert manifest["newly_completed_executions"] == 2
    assert manifest["carried_provider_calls"] == 4
    assert manifest["new_provider_calls"] == 2
    assert manifest["historical_stop_reason"] == "pre_provider_failure"
    assert manifest["active_stop_reason"] == "complete"
    assert manifest["resume_allowed"] is True


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
        (lambda value: value.update(call_ledger=[{"ordinal": 1}]), "call ledger"),
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
    assert value["next_ordinal"] == 5
    assert value["carried_provider_calls"] == 4
    assert value["historical_stop_reason"] == "pre_provider_failure"
    assert value["active_stop_reason"] is None
    assert value["resume_allowed"] is True


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.update(historical_stop_reason="unknown"), "resume policy"),
        (lambda value: value.update(call_ledger=[value["call_ledger"][0]] * 4), "call identity"),
        (lambda value: value["completed_executions"].__setitem__(0, None), "execution"),
        (
            lambda value: value["completed_executions"][0].update(observed_usd="0.025946"),
            "execution mismatch",
        ),
    ],
)
def test_additional_checkpoint_fail_closed_paths(
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
    target = tmp_path / "invalid.json"
    target.write_bytes(canonical_json(value))
    with pytest.raises(ValueError, match=message):
        load_checkpoint(target)


def test_noncanonical_and_unfingerprinted_checkpoints_fail_closed(
    repository_root: Path, tmp_path: Path
) -> None:
    canonical = (repository_root / CHECKPOINT).read_bytes()
    noncanonical = tmp_path / "noncanonical.json"
    noncanonical.write_bytes(canonical + b"\n")
    with pytest.raises(ValueError, match="non-canonical"):
        load_checkpoint(noncanonical)
    value = json.loads(canonical)
    value["checkpoint_fingerprint"] = "0" * 64
    unfingerprinted = tmp_path / "unfingerprinted.json"
    unfingerprinted.write_bytes(canonical_json(value))
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        load_checkpoint(unfingerprinted)


@pytest.mark.parametrize(
    "reason",
    [
        ResumeStopReason.AUTHENTICATION_FAILURE,
        ResumeStopReason.BILLING_FAILURE,
        ResumeStopReason.QUOTA_FAILURE,
        ResumeStopReason.BUDGET_CEILING,
        ResumeStopReason.IDENTITY_MISMATCH,
        ResumeStopReason.LEAKAGE_OR_SECURITY_FAILURE,
        ResumeStopReason.CORRUPT_CHECKPOINT,
        ResumeStopReason.INCOMPLETE_CLEANUP,
    ],
)
def test_fatal_resume_stop_reasons_remain_active(reason: ResumeStopReason) -> None:
    policy = classify_resume_stop(reason, ResumeStopClassification.FATAL)
    assert policy.resume_allowed is False
    assert policy.historical_stop_reason is reason
    assert policy.active_stop_reason is reason


def test_execution_failure_is_not_arbitrarily_cleared() -> None:
    policy = classify_resume_stop(
        ResumeStopReason.EXECUTION_FAILURE, ResumeStopClassification.FATAL
    )
    assert policy.resume_allowed is False
    assert policy.active_stop_reason is ResumeStopReason.EXECUTION_FAILURE


def test_fatal_checkpoint_stops_before_executor(repository_root: Path, tmp_path: Path) -> None:
    checkpoint = load_checkpoint(repository_root / CHECKPOINT)
    checkpoint["historical_stop_reason"] = "authentication_failure"
    checkpoint["historical_stop_classification"] = "fatal"
    checkpoint["active_stop_reason"] = "authentication_failure"
    checkpoint["resume_allowed"] = False
    configuration = load_phase13_provider_configuration(
        repository_root / "configs/experiments/phase13-provider.json"
    )
    executor = FakeExecutor(PROTOCOL)
    with pytest.raises(ControlledStop):
        run_frozen_experiment(
            protocol_fingerprint=PROTOCOL,
            configuration=configuration,
            executor=executor,
            artifacts=SourceFreeArtifacts(tmp_path / "evidence"),
            checkpoint=checkpoint,
        )
    assert executor.requests == []


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
    assert state.calls_started == 1
    with pytest.raises(ValueError, match="duplicate"):
        _register_call(state, "a" * 64, completed=True, usage=True)
