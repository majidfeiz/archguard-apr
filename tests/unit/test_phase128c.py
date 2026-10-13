import json
import stat
import zipfile
from pathlib import Path

import pytest

from archguard.domain.canonical import canonical_json
from archguard.domain.orchestration import fingerprint
from archguard.infrastructure import phase128c_evidence as evidence
from archguard.infrastructure.architecture_profiles import LocalArchitectureProfiles
from archguard.infrastructure.phase128b_evidence import BUGGY_REVISION, validate_imported_evidence
from archguard.infrastructure.phase128c_evidence import (
    AMENDED_PROFILE_FINGERPRINT,
    ARCHIVE_MEMBERS,
    OLD_PROFILE_FINGERPRINT,
    finalize_cleanup,
    import_archive,
    package,
    produce,
    validate_archive,
    validate_directory,
)
from archguard.infrastructure.readiness_artifacts import load_human_decision

GRAPH_FINGERPRINT = "e08af7f18e793a17e06721127ebf43d791c299a92702dba5c06d932ab527ab1e"
CANONICAL_GRAPH_FINGERPRINT = "b1c318faba70d50225ceba74254edb18727013291de8607695334f8f0a98802c"
ACQUISITION_FINGERPRINT = "b5820205e5339b0a64a7efdfef6bd74cb71b90d58a18f90fa9847af4123f4c1f"


def test_historical_human_amend_decision_is_strictly_bound(repository_root: Path) -> None:
    decision = load_human_decision(
        repository_root / "research/reviews/pysnooper-profile-amend-decision.json"
    )
    assert decision.decision.value == "AMEND"
    assert decision.reviewed_fingerprint == OLD_PROFILE_FINGERPRINT
    assert decision.evidence_binding == {
        "graph_fingerprint": GRAPH_FINGERPRINT,
        "canonical_graph_fingerprint": CANONICAL_GRAPH_FINGERPRINT,
        "acquisition_fingerprint": ACQUISITION_FINGERPRINT,
        "buggy_revision": "e21a31162f4c54be693d8ca8260e42393b39abd3",
        "task_id": "PySnooper-2",
    }
    assert not decision.approves(OLD_PROFILE_FINGERPRINT)


def test_amended_profile_adds_only_exact_tooling_modules(repository_root: Path) -> None:
    profiles = LocalArchitectureProfiles()
    old = profiles.load(repository_root / "configs/external-profiles/pysnooper-micro-pilot.yaml")
    new = profiles.load(
        repository_root / "configs/external-profiles/pysnooper-micro-pilot-amended-v2.yaml"
    )
    old_components = {c.id: c for c in old.components}
    new_components = {c.id: c for c in new.components}
    assert new.profile_fingerprint == AMENDED_PROFILE_FINGERPRINT != old.profile_fingerprint
    assert set(new_components) - set(old_components) == {"project-tooling"}
    assert all(new_components[name] == component for name, component in old_components.items())
    tooling = new_components["project-tooling"]
    assert [(s.type, s.value) for s in tooling.selectors] == [
        ("module_exact", "misc.generate_authors"),
        ("module_exact", "setup"),
    ]
    assert all("project-tooling" not in repr(rule) for rule in new.rules)


def test_old_evidence_remains_bound_to_old_profile(repository_root: Path) -> None:
    imported = validate_imported_evidence(
        repository_root / "research/evidence/phase-12.8b-license-graph.json"
    )
    assert imported["manifest"]["profile_fingerprint"] == OLD_PROFILE_FINGERPRINT


def test_protocol_approved_and_scientific_phase_ready(repository_root: Path) -> None:
    protocol = json.loads((repository_root / "research/reviews/protocol-decision.json").read_text())
    facts = json.loads((repository_root / "research/readiness-facts.json").read_text())
    assert protocol["decision"] == "APPROVE"
    assert facts["architecture_analysis_complete"] is True
    assert facts["profiles_frozen"] is True


def test_workflow_has_runtime_temp_exact_artifact_and_limits(repository_root: Path) -> None:
    raw = (repository_root / ".github/workflows/phase-12-8c-profile-reevaluation.yml").read_text()
    assert "workflow_dispatch:" in raw and "runs-on: ubuntu-24.04" in raw
    assert "permissions:\n  contents: read" in raw
    assert "${RUNNER_TEMP}" in raw and "${{ runner.temp }}" not in raw
    assert "retention-days: 14" in raw
    assert "archguard-phase-12-8c-profile-reevaluation-${{ github.run_id }}" in raw
    assert "timeout-minutes: 30" in raw and "timeout 15m" in raw


def test_readiness_workflow_validates_scientific_and_operational_readiness(
    repository_root: Path,
) -> None:
    raw = (repository_root / ".github/workflows/phase-12-8-readiness.yml").read_text()
    assert 'pysnooper-profile-decision.json)" = APPROVE' in raw
    assert 'protocol-decision.json)" = APPROVE' in raw
    assert 'pysnooper_amended_profile_status research/readiness-facts.json)" = FROZEN' in raw
    assert 'architecture_analysis_complete research/readiness-facts.json)" = true' in raw
    assert 'profiles_frozen research/readiness-facts.json)" = true' in raw
    assert ".phase_13_scientifically_ready" in raw
    assert '.phase_13_operationally_ready "$RUNNER_TEMP/gate.json")" = true' in raw
    assert ".blocker_codes == []" in raw


@pytest.mark.parametrize("unsafe", ["../manifest.json", "nested/manifest.json"])
def test_archive_rejects_traversal_and_nested_paths(tmp_path: Path, unsafe: str) -> None:
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as target:
        target.writestr(unsafe, b"{}")
    with pytest.raises(ValueError, match="allowlist"):
        validate_archive(archive)


def test_archive_rejects_duplicates_and_symlinks(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.zip"
    with zipfile.ZipFile(duplicate, "w") as target:
        for name in ARCHIVE_MEMBERS:
            target.writestr(name, b"{}")
        target.writestr("manifest.json", b"{}")
    with pytest.raises(ValueError, match="allowlist"):
        validate_archive(duplicate)
    symlink = tmp_path / "symlink.zip"
    with zipfile.ZipFile(symlink, "w") as target:
        for name in ARCHIVE_MEMBERS:
            info = zipfile.ZipInfo(name)
            info.external_attr = (
                (stat.S_IFLNK | 0o777) if name == "manifest.json" else 0o100644
            ) << 16
            target.writestr(info, b"{}")
    with pytest.raises(ValueError, match="unsafe"):
        validate_archive(symlink)


def test_evidence_round_trip_is_deterministic_and_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, repository_root: Path
) -> None:
    external, root = tmp_path / "external", tmp_path / "evidence"
    external.mkdir()
    evaluation = {
        "internal_module_count": 14,
        "assigned_module_count": 14,
        "unassigned_module_count": 0,
        "ambiguous_module_count": 0,
        "enabled_rules": 5,
        "disabled_rules": 0,
        "evaluated_rules": 5,
        "skipped_rules": 0,
        "dependency_violation_count": 0,
        "external_dependency_violation_count": 0,
        "cycle_violation_count": 0,
        "total_violation_count": 0,
        "error_violation_count": 0,
        "warning_violation_count": 0,
        "informational_violation_count": 0,
        "partial": False,
        "passed": True,
    }
    graph = {
        "modules": 14,
        "assigned_modules": 14,
        "unassigned_modules": 0,
        "ambiguous_modules": 0,
        "canonical_graph_fingerprint": "a" * 64,
        "snapshot_fingerprint": "b" * 64,
        "constraint_evaluation": evaluation,
    }
    monkeypatch.setattr(evidence, "acquire", lambda *_args: 123)
    monkeypatch.setattr(
        evidence,
        "generate_graph_evidence",
        lambda *_args: (graph, b'{"deterministic":true}\n'),
    )

    manifest = produce(external, root, repository_root, "123")
    assert manifest["profile_fingerprint"] == AMENDED_PROFILE_FINGERPRINT
    assert set(path.name for path in root.iterdir()) == ARCHIVE_MEMBERS
    external.rmdir()
    finalize_cleanup(root, external)
    assert validate_directory(root)["task_id"] == "PySnooper-2"

    archive = tmp_path / "evidence.zip"
    package(root, archive)
    assert validate_archive(archive)["buggy_revision"] == BUGGY_REVISION
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    assert import_archive(archive, first) == import_archive(archive, second)
    assert import_archive(archive, first)["schema"].endswith("evidence-import/v1")

    graph_path = root / "graph-evidence.json"
    original = graph_path.read_bytes()
    graph_path.write_bytes(original.replace(b'"assigned_modules":14', b'"assigned_modules":13'))
    evidence.write_checksums(root)
    with pytest.raises(ValueError, match="fingerprint|contradictory"):
        validate_directory(root)


@pytest.mark.parametrize(
    ("field", "value"),
    [("buggy_revision", "b" * 40), ("profile_fingerprint", OLD_PROFILE_FINGERPRINT)],
)
def test_validator_rejects_wrong_revision_and_profile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    repository_root: Path,
    field: str,
    value: str,
) -> None:
    root = _valid_evidence(monkeypatch, tmp_path, repository_root)
    path = root / "manifest.json"
    record = json.loads(path.read_text())
    record[field] = value
    record["fingerprint"] = fingerprint({k: v for k, v in record.items() if k != "fingerprint"})
    path.write_bytes(canonical_json(record))
    evidence.write_checksums(root)
    with pytest.raises(ValueError, match="contradictory"):
        validate_directory(root)


def test_validator_rejects_gold_and_secret_leakage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, repository_root: Path
) -> None:
    root = _valid_evidence(monkeypatch, tmp_path, repository_root)
    path = root / "security-scan-summary.json"
    record = json.loads(path.read_text())
    record["gold_patch"] = "api_key"
    record["fingerprint"] = fingerprint({k: v for k, v in record.items() if k != "fingerprint"})
    path.write_bytes(canonical_json(record))
    evidence.write_checksums(root)
    with pytest.raises(ValueError, match="leakage"):
        validate_directory(root)


def _valid_evidence(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, repository_root: Path) -> Path:
    external, root = tmp_path / "external", tmp_path / "evidence"
    external.mkdir()
    summary = {
        "modules": 14,
        "assigned_modules": 14,
        "unassigned_modules": 0,
        "ambiguous_modules": 0,
        "canonical_graph_fingerprint": "a" * 64,
        "snapshot_fingerprint": "b" * 64,
        "constraint_evaluation": {
            "assigned_module_count": 14,
            "unassigned_module_count": 0,
            "ambiguous_module_count": 0,
            "skipped_rules": 0,
        },
    }
    monkeypatch.setattr(evidence, "acquire", lambda *_args: 1)
    monkeypatch.setattr(evidence, "generate_graph_evidence", lambda *_args: (summary, b"same"))
    produce(external, root, repository_root, "test")
    external.rmdir()
    finalize_cleanup(root, external)
    return root


def test_production_rejects_incomplete_assignments(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, repository_root: Path
) -> None:
    external = tmp_path / "external"
    external.mkdir()
    monkeypatch.setattr(evidence, "acquire", lambda *_args: 1)
    incomplete = {
        "modules": 14,
        "assigned_modules": 13,
        "unassigned_modules": 1,
        "ambiguous_modules": 0,
        "constraint_evaluation": {"skipped_rules": 1},
    }
    monkeypatch.setattr(evidence, "generate_graph_evidence", lambda *_args: (incomplete, b"same"))
    with pytest.raises(ValueError, match="AMENDMENT_REQUIRED"):
        produce(external, tmp_path / "evidence", repository_root, "local")
