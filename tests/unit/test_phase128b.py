import json
import stat
import zipfile
from dataclasses import asdict
from pathlib import Path

import pytest

from archguard.domain.canonical import canonical_json
from archguard.domain.phase128b import (
    ACQUISITION_SCHEMA,
    ARCHIVE_MEMBERS,
    DETERMINISM_SCHEMA,
    GRAPH_EVIDENCE_SCHEMA,
    LICENSE_REGISTRY_SCHEMA,
    MANIFEST_SCHEMA,
    ImmutableRevision,
    Phase128BManifest,
    fingerprinted,
)
from archguard.domain.readiness import readiness_report
from archguard.infrastructure import phase128b_evidence as evidence

SHA = "a" * 64


def write_valid_directory(root: Path) -> Path:
    root.mkdir()
    acquisition = fingerprinted(
        ACQUISITION_SCHEMA,
        {
            "download_ceiling_bytes": evidence.MAX_DOWNLOAD_BYTES,
            "measured_disk_bytes": 1,
            "records": [
                {
                    "subject": item.subject,
                    "repository": item.repository,
                    "revision": item.revision,
                }
                for item in evidence.SPECS
            ],
        },
    )
    licenses = fingerprinted(
        LICENSE_REGISTRY_SCHEMA,
        {"records": [], "benchmark_task_redistribution": "UNRESOLVED"},
    )
    graph = fingerprinted(
        GRAPH_EVIDENCE_SCHEMA,
        {
            "repository_revision": evidence.BUGGY_REVISION,
            "profile_fingerprint": evidence.PROFILE_FINGERPRINT,
            "acquisition_manifest_fingerprint": acquisition["fingerprint"],
        },
    )
    manifest = Phase128BManifest(
        MANIFEST_SCHEMA,
        "PySnooper-2",
        "PySnooper",
        evidence.BUGGY_REVISION,
        evidence.FIXED_REVISION,
        evidence.BUGSINPY_REVISION,
        str(acquisition["fingerprint"]),
        str(licenses["fingerprint"]),
        str(graph["fingerprint"]),
        evidence.PROFILE_FINGERPRINT,
        "123",
        "external-evidence",
        False,
    )
    values: dict[str, object] = {
        "manifest.json": asdict(manifest),
        "acquisition-summary.json": acquisition,
        "license-evidence.json": licenses,
        "graph-evidence.json": graph,
        "graph-determinism.json": fingerprinted(
            DETERMINISM_SCHEMA, {"independent_runs": 2, "byte_identical": True}
        ),
        "security-scan-summary.json": fingerprinted(
            "archguard.phase-12.8b-security-scan/v1", {"status": "PASSED"}
        ),
        "cleanup-summary.json": fingerprinted(
            "archguard.phase-12.8b-cleanup/v1", {"status": "COMPLETE"}
        ),
        "readiness-summary.json": fingerprinted(
            "archguard.phase-12.8b-readiness-summary/v1",
            {
                "phase_13_ready": False,
                "architecture_analysis_complete": False,
                "profile_status": "REVIEW_REQUIRED",
                "protocol_status": "REVIEW_REQUIRED",
                "resolved_blocker_codes": ["GRAPH_EVIDENCE_EXTERNAL_EXECUTION_REQUIRED"],
            },
        ),
    }
    for name, value in values.items():
        (root / name).write_bytes(canonical_json(value))
    evidence.write_checksums(root)
    return root


def test_immutable_revision_rejects_abbreviated_and_mutable_identity() -> None:
    with pytest.raises(ValueError, match="Git SHA"):
        ImmutableRevision("pilot", "https://github.com/org/repo.git", "deadbeef")
    with pytest.raises(ValueError, match="Git SHA"):
        ImmutableRevision("pilot", "https://github.com/org/repo.git", "main")
    with pytest.raises(ValueError, match="unsupported"):
        ImmutableRevision("pilot", "https://example.invalid/repo.git", "a" * 40)


def test_acquisition_rejects_wrong_head(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(evidence, "_run_git", lambda *args, **kwargs: "b" * 40)
    with pytest.raises(ValueError, match="revision mismatch"):
        evidence.acquire(
            ImmutableRevision("pilot", "https://github.com/org/repo.git", "a" * 40),
            tmp_path / "checkout",
        )


def test_external_paths_reject_repository_and_overlapping_roots(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    with pytest.raises(ValueError, match="outside"):
        evidence.validate_external_paths(repository / "external", tmp_path / "output", repository)
    with pytest.raises(ValueError, match="distinct"):
        evidence.validate_external_paths(
            tmp_path / "external", tmp_path / "external/out", repository
        )


def test_acquisition_rejects_symlink_escape(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "checkout"
    root.mkdir()
    (root / "escape").symlink_to(tmp_path / "outside")
    (tmp_path / "outside").write_text("outside", encoding="utf-8")

    def git(arguments: list[str], _cwd: Path, capture: bool = False) -> str:
        return "https://github.com/org/repo.git" if "get-url" in arguments else "origin"

    monkeypatch.setattr(evidence, "_run_git", git)
    with pytest.raises(ValueError, match="symlink escapes"):
        evidence.validate_acquisition_tree(root, "https://github.com/org/repo.git")


def test_license_audit_preserves_unresolved_records(tmp_path: Path) -> None:
    for name in ("pysnooper-buggy", "bugsinpy-metadata", "swe-bench-framework"):
        (tmp_path / name).mkdir()
    result = evidence.audit_licenses(tmp_path, "2026-01-01T00:00:00Z")
    assert result["benchmark_task_redistribution"] == "UNRESOLVED"
    assert all(record["audit_status"] == "UNRESOLVED" for record in result["records"])


def test_archive_round_trip_has_exact_allowlist(tmp_path: Path) -> None:
    source = write_valid_directory(tmp_path / "source")
    archive = tmp_path / "evidence.zip"
    evidence.create_evidence_zip(source, archive)
    assert evidence.validate_evidence_zip(archive)["task_id"] == "PySnooper-2"
    with zipfile.ZipFile(archive) as value:
        assert set(value.namelist()) == ARCHIVE_MEMBERS


def test_import_is_deterministic_idempotent_and_rejects_contradiction(tmp_path: Path) -> None:
    source = write_valid_directory(tmp_path / "source")
    archive = tmp_path / "evidence.zip"
    evidence.create_evidence_zip(source, archive)
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    evidence.import_evidence_zip(archive, first)
    evidence.import_evidence_zip(archive, second)
    before = first.read_bytes()
    evidence.import_evidence_zip(archive, first)

    assert first.read_bytes() == second.read_bytes() == before
    assert evidence.validate_imported_evidence(first)["schema"] == evidence.IMPORTED_EVIDENCE_SCHEMA
    first.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="contradictory"):
        evidence.import_evidence_zip(archive, first)


@pytest.mark.parametrize("unsafe", ["../escape.json", "/absolute.json"])
def test_archive_rejects_traversal(tmp_path: Path, unsafe: str) -> None:
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as target:
        target.writestr(unsafe, b"{}\n")
    with pytest.raises(ValueError, match="allowlist"):
        evidence.validate_evidence_zip(archive)


def test_archive_rejects_duplicates_and_symlinks(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.zip"
    with zipfile.ZipFile(duplicate, "w") as target:
        target.writestr("manifest.json", b"{}\n")
        target.writestr("manifest.json", b"{}\n")
    with pytest.raises(ValueError, match="allowlist"):
        evidence.validate_evidence_zip(duplicate)

    source = write_valid_directory(tmp_path / "source")
    archive = tmp_path / "symlink.zip"
    with zipfile.ZipFile(archive, "w") as target:
        for name in sorted(ARCHIVE_MEMBERS):
            info = zipfile.ZipInfo(name)
            info.external_attr = (
                (stat.S_IFLNK | 0o777) if name == "manifest.json" else 0o100644
            ) << 16
            target.writestr(info, (source / name).read_bytes())
    with pytest.raises(ValueError, match="unsafe"):
        evidence.validate_evidence_zip(archive)


def test_source_gold_log_and_secret_leakage_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    root.mkdir()
    for name, content in (
        ("source.py", b"print('source')\n"),
        ("gold.json", b'{"value":"diff --git a/x b/x"}\n'),
        ("raw.log", b"raw log\n"),
        ("secret.json", b'{"value":"' + evidence.PRIVATE_KEY_MARKER + b'"}\n'),
    ):
        path = root / name
        path.write_bytes(content)
        with pytest.raises(ValueError):
            evidence.scan_source_free(root)
        path.unlink()


def test_graph_revision_profile_binding_and_phase13_false(tmp_path: Path) -> None:
    source = write_valid_directory(tmp_path / "source")
    graph_path = source / "graph-evidence.json"
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    graph["repository_revision"] = "b" * 40
    graph_path.write_bytes(canonical_json(graph))
    evidence.write_checksums(source)
    with pytest.raises(ValueError, match="fingerprint|contradictory"):
        evidence.validate_evidence_directory(source)


def test_cleanup_requires_removed_external_root(tmp_path: Path) -> None:
    source = write_valid_directory(tmp_path / "source")
    external = tmp_path / "external"
    external.mkdir()
    with pytest.raises(ValueError, match="not cleaned"):
        evidence.finalize_cleanup(source, external)
    external.rmdir()
    assert evidence.finalize_cleanup(source, external)["status"] == "COMPLETE"


def test_graph_generation_is_byte_identical_and_bound_to_profile(
    tmp_path: Path, repository_root: Path
) -> None:
    source = tmp_path / "pysnooper-buggy"
    package = source / "pysnooper"
    tests = source / "tests"
    package.mkdir(parents=True)
    tests.mkdir()
    for name in ("__init__.py", "tracer.py", "variables.py", "pycompat.py", "utils.py"):
        (package / name).write_text("VALUE = 1\n", encoding="utf-8")
    (tests / "test_public.py").write_text("import pysnooper\n", encoding="utf-8")
    profile = repository_root / "configs/external-profiles/pysnooper-micro-pilot.yaml"

    first, first_raw = evidence.generate_graph_evidence(source, tmp_path / "first", profile)
    second, second_raw = evidence.generate_graph_evidence(source, tmp_path / "second", profile)

    assert first_raw == second_raw
    assert first["canonical_graph_fingerprint"] == second["canonical_graph_fingerprint"]
    assert first["profile_fingerprint"] == evidence.PROFILE_FINGERPRINT
    assert first["repository_revision"] == evidence.BUGGY_REVISION


def test_tracked_import_identity_and_partial_status(repository_root: Path) -> None:
    path = repository_root / "research/evidence/phase-12.8b-license-graph.json"
    imported = evidence.validate_imported_evidence(path)
    graph = imported["evidence"]["graph_evidence"]
    licenses = imported["evidence"]["license_evidence"]

    assert imported["archive_sha256"] == (
        "5a793348ba02ef002ee1cadd826d2dcc049089d4da928bbf41e1eeb6b90c8cef"
    )
    assert imported["fingerprint"] == (
        "6277810062743dfd274fc0e03a51a0d6f29b79ba6da45ab9fbabff99b0197648"
    )
    assert imported["manifest"]["github_run_id"] == "37152285061"
    assert graph["fingerprint"] == (
        "e08af7f18e793a17e06721127ebf43d791c299a92702dba5c06d932ab527ab1e"
    )
    assert graph["constraint_evaluation"]["partial"] is True
    assert graph["constraint_evaluation"]["passed"] is False
    assert graph["unassigned_modules"] == 2
    assert licenses["benchmark_task_redistribution"] == "UNRESOLVED"


def test_imported_evidence_and_provider_configuration_clear_blockers(
    repository_root: Path,
) -> None:
    facts = json.loads((repository_root / "research/readiness-facts.json").read_text())
    report = readiness_report(facts)

    assert "GRAPH_EVIDENCE_EXTERNAL_EXECUTION_REQUIRED" not in report["blocker_codes"]
    assert report["phase_13_ready"] is True
    assert report["phase_12_complete"] is True
    assert report["phase_13_scientifically_ready"] is True
    assert report["blocker_codes"] == []


def test_profile_is_amended_protocol_pending_and_import_is_source_free(
    repository_root: Path,
) -> None:
    profile = json.loads(
        (repository_root / "research/reviews/pysnooper-profile-decision.json").read_text()
    )
    protocol = json.loads((repository_root / "research/reviews/protocol-decision.json").read_text())
    assert profile["decision"] == "APPROVE"
    assert profile["reviewer_name"] == "user-authorized human reviewer"
    assert profile["review_timestamp"]
    historical = json.loads(
        (repository_root / "research/reviews/pysnooper-profile-amend-decision.json").read_text()
    )
    assert historical["decision"] == "AMEND"
    assert protocol["decision"] == "APPROVE"
    assert protocol["reviewer_name"] == "Majid Feiz"
    assert protocol["review_timestamp"]

    evidence_root = repository_root / "research/evidence"
    assert not list(evidence_root.glob("*.zip"))
    raw = (evidence_root / "phase-12.8b-license-graph.json").read_bytes()
    assert not any(marker in raw for marker in evidence.SOURCE_MARKERS)
    assert b'"phase_13_ready":false' in raw
