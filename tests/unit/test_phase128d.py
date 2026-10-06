import hashlib
import json
from pathlib import Path

import pytest

from archguard.domain.canonical import canonical_json
from archguard.domain.orchestration import fingerprint
from archguard.infrastructure.phase128c_evidence import (
    AMENDED_PROFILE_FINGERPRINT,
    import_archive,
    package,
    write_checksums,
)
from archguard.infrastructure.phase128d_records import (
    CANONICAL_ARCHIVE_SHA256,
    GITHUB_ARTIFACT_SHA256,
    validate_freeze_record,
    validate_imported_evidence,
)
from archguard.infrastructure.readiness_artifacts import load_human_decision


@pytest.fixture
def canonical_phase128c_archive(repository_root: Path, tmp_path: Path) -> Path:
    imported = json.loads(
        (repository_root / "research/evidence/phase-12.8c-profile-reevaluation.json").read_text()
    )
    root = tmp_path / "evidence"
    root.mkdir()
    for key, value in imported["evidence"].items():
        (root / f"{key.replace('_', '-')}.json").write_bytes(canonical_json(value))
    write_checksums(root)
    archive = tmp_path / "canonical.zip"
    package(root, archive)
    return archive


def test_tracked_import_and_distinct_container_hashes(repository_root: Path) -> None:
    imported = validate_imported_evidence(
        repository_root / "research/evidence/phase-12.8c-profile-reevaluation.json"
    )
    assert imported["archive_sha256"] == CANONICAL_ARCHIVE_SHA256
    assert CANONICAL_ARCHIVE_SHA256 != GITHUB_ARTIFACT_SHA256
    assert imported["fingerprint"] == (
        "2eb422f3a48222aca7f664537f0fad41441a1841886b3a61280af00e50a9639c"
    )


def test_three_pass_import_idempotence_and_contradiction(
    tmp_path: Path, canonical_phase128c_archive: Path
) -> None:
    assert hashlib.sha256(canonical_phase128c_archive.read_bytes()).hexdigest() == (
        CANONICAL_ARCHIVE_SHA256
    )
    outputs = [tmp_path / f"import-{index}.json" for index in range(3)]
    for output in outputs:
        import_archive(canonical_phase128c_archive, output)
    assert len({output.read_bytes() for output in outputs}) == 1
    before = outputs[0].read_bytes()
    import_archive(canonical_phase128c_archive, outputs[0])
    assert outputs[0].read_bytes() == before
    contradictory = tmp_path / "contradictory.json"
    contradictory.write_text("{}\n")
    with pytest.raises(ValueError, match="contradictory"):
        import_archive(canonical_phase128c_archive, contradictory)


def test_approval_is_bound_and_historical_amend_is_preserved(repository_root: Path) -> None:
    approval = load_human_decision(
        repository_root / "research/reviews/pysnooper-profile-decision.json"
    )
    history_path = repository_root / "research/reviews/pysnooper-profile-amend-decision.json"
    history = load_human_decision(history_path)
    assert approval.decision.value == "APPROVE"
    assert approval.approves(AMENDED_PROFILE_FINGERPRINT)
    assert approval.approval_binding is not None
    assert approval.approval_binding["canonical_archive_sha256"] == CANONICAL_ARCHIVE_SHA256
    assert (
        approval.previous_decision_sha256 == hashlib.sha256(history_path.read_bytes()).hexdigest()
    )
    assert history.decision.value == "AMEND"


def test_freeze_recompiles_and_rejects_profile_drift(repository_root: Path, tmp_path: Path) -> None:
    args = (
        repository_root / "research/profiles/pysnooper-profile-freeze.json",
        repository_root / "configs/external-profiles/pysnooper-micro-pilot-amended-v2.yaml",
        repository_root / "research/reviews/pysnooper-profile-decision.json",
        repository_root / "research/evidence/phase-12.8c-profile-reevaluation.json",
    )
    freeze = validate_freeze_record(*args)
    assert freeze["profile_fingerprint"] == AMENDED_PROFILE_FINGERPRINT
    drift = tmp_path / "profile.yaml"
    drift.write_bytes(args[1].read_bytes().replace(b"setup}", b"changed}"))
    with pytest.raises(ValueError, match="drift|binding"):
        validate_freeze_record(args[0], drift, args[2], args[3])


def test_approval_rejects_old_profile_binding(repository_root: Path, tmp_path: Path) -> None:
    source = repository_root / "research/reviews/pysnooper-profile-decision.json"
    value = json.loads(source.read_text())
    value["reviewed_fingerprint"] = (
        "e2694d6a8016382036a3670476d75a0ca16d7f9872678156d16fba6de0f441f1"
    )
    path = tmp_path / "decision.json"
    path.write_bytes(canonical_json(value))
    with pytest.raises(ValueError, match="mismatch"):
        load_human_decision(path)


def test_import_fingerprint_tampering_fails_closed(repository_root: Path, tmp_path: Path) -> None:
    source = repository_root / "research/evidence/phase-12.8c-profile-reevaluation.json"
    value = json.loads(source.read_text())
    value["evidence"]["graph_evidence"]["assigned_modules"] = 13
    value["fingerprint"] = fingerprint({k: v for k, v in value.items() if k != "fingerprint"})
    path = tmp_path / "import.json"
    path.write_bytes(canonical_json(value))
    with pytest.raises(ValueError, match="contradictory"):
        validate_imported_evidence(path)


def test_protocol_unchanged_and_global_phase13_false(repository_root: Path) -> None:
    protocol = json.loads((repository_root / "research/reviews/protocol-decision.json").read_text())
    facts = json.loads((repository_root / "research/readiness-facts.json").read_text())
    assert protocol["decision"] == "PENDING"
    assert facts["pysnooper_architecture_analysis_complete"] is True
    assert facts["pysnooper_profile_approved"] is True
    assert facts["pysnooper_profile_frozen"] is True
    assert facts["architecture_analysis_complete"] is False
    assert facts["profiles_frozen"] is False
