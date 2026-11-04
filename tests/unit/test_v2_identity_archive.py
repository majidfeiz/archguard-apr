import hashlib
import json
import stat
import zipfile
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from archguard.domain.canonical import canonical_json
from archguard.domain.v2_identity import (
    ACQUISITION_CEILING_BYTES,
    AUTHORIZED_REPOSITORY,
    AUTHORIZED_REVISION,
    IDENTITY_SCHEMA,
    TASK_MANIFEST_FINGERPRINT,
)
from archguard.entrypoints.cli.app import app
from archguard.infrastructure.v2_identity_archive import (
    import_identity_archive,
    validate_identity_archive,
    write_identity_archive,
)

pytestmark = pytest.mark.unit
runner = CliRunner()


def identified(value: dict[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result["fingerprint"] = hashlib.sha256(canonical_json(value)).hexdigest()
    return result


def evidence(**changes: object) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema": IDENTITY_SCHEMA,
        "project": "PySnooper",
        "task_id": "PySnooper-2",
        "authorized_repository_url": AUTHORIZED_REPOSITORY,
        "requested_revision": AUTHORIZED_REVISION,
        "resolved_revision": AUTHORIZED_REVISION,
        "git_object_format": "sha1",
        "root_tree_object_id": "a" * 40,
        "ls_tree_sha256": "b" * 64,
        "tree_entry_count": 42,
        "acquisition_byte_count": 12345,
        "acquisition_ceiling": ACQUISITION_CEILING_BYTES,
        "checkout_performed": False,
        "source_files_opened": False,
        "hooks_executed": False,
        "submodules_initialized": False,
        "lfs_smudge_executed": False,
        "target_code_executed": False,
        "provider_calls": 0,
        "scientific_executions": 0,
        "github_run_id": "123456",
        "github_job_identity": "identity-only-acquisition",
        "runner_os": "Linux",
        "runner_architecture": "X64",
        "cleanup_result": "SUCCEEDED",
    }
    value.update(changes)
    return identified(value)


def archive(path: Path, identity: dict[str, Any] | None = None) -> Path:
    tree = canonical_json(identity or evidence())
    cleanup = canonical_json(
        identified(
            {
                "schema": "archguard.v2-identity-cleanup/v1",
                "cleanup_result": "SUCCEEDED",
                "temporary_repository_removed": True,
                "credential_material_present": False,
            }
        )
    )
    manifest = canonical_json(
        identified(
            {
                "schema": "archguard.v2-identity-archive-manifest/v1",
                "task_manifest_fingerprint": TASK_MANIFEST_FINGERPRINT,
                "tree_identity_sha256": hashlib.sha256(tree).hexdigest(),
                "cleanup_summary_sha256": hashlib.sha256(cleanup).hexdigest(),
                "root_tree_object_id": (identity or evidence())["root_tree_object_id"],
                "ls_tree_sha256": (identity or evidence())["ls_tree_sha256"],
                "tree_entry_count": (identity or evidence())["tree_entry_count"],
            }
        )
    )
    files = {
        "cleanup-summary.json": cleanup,
        "manifest.json": manifest,
        "tree-identity.json": tree,
    }
    files["SHA256SUMS"] = "".join(
        f"{hashlib.sha256(files[name]).hexdigest()}  {name}\n" for name in sorted(files)
    ).encode()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as target:
        for name, payload in files.items():
            target.writestr(name, payload)
    return path


def test_valid_archive_and_idempotent_import(tmp_path: Path) -> None:
    source = archive(tmp_path / "valid.zip")
    assert validate_identity_archive(source).root_tree_object_id == "a" * 40
    output = tmp_path / "identity.json"
    first = import_identity_archive(source, output)
    assert import_identity_archive(source, output) == first
    assert output.read_bytes() == canonical_json(first.__dict__)


def test_identity_cli_validates_and_imports(tmp_path: Path) -> None:
    source = archive(tmp_path / "valid.zip")
    output = tmp_path / "identity.json"
    validated = runner.invoke(
        app, ["experiment", "v2", "identity", "validate", "--archive", str(source)]
    )
    imported = runner.invoke(
        app,
        [
            "experiment",
            "v2",
            "identity",
            "import",
            "--archive",
            str(source),
            "--output",
            str(output),
        ],
    )
    assert validated.exit_code == imported.exit_code == 0
    assert json.loads(validated.stdout)["provider_calls"] == 0
    assert output.exists()


def test_production_archive_regeneration_is_byte_identical(tmp_path: Path) -> None:
    value = evidence()
    value.pop("fingerprint")
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    write_identity_archive(first, value)
    write_identity_archive(second, value)
    assert first.read_bytes() == second.read_bytes()


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"authorized_repository_url": "https://example.invalid/repo.git"}, "wrong repository"),
        ({"requested_revision": "c" * 40}, "wrong requested revision"),
        ({"requested_revision": "814abc3"}, "wrong requested revision"),
        ({"resolved_revision": "c" * 40}, "wrong resolved revision"),
        ({"task_id": "PySnooper-3"}, "wrong task"),
        ({"root_tree_object_id": "z" * 40}, "invalid root tree"),
        ({"cleanup_result": "FAILED"}, "cleanup failed"),
        ({"target_code_executed": True}, "forbidden target operation"),
        ({"provider_calls": 1}, "provider call"),
    ],
)
def test_semantic_contradictions_fail_closed(
    tmp_path: Path, changes: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_identity_archive(archive(tmp_path / "bad.zip", evidence(**changes)))


def test_sha_leakage_and_contradictory_overwrite(tmp_path: Path) -> None:
    source = archive(tmp_path / "valid.zip")
    with zipfile.ZipFile(source) as original:
        files = {name: original.read(name) for name in original.namelist()}
    bad_sha = tmp_path / "bad-sha.zip"
    manifest = json.loads(files["manifest.json"])
    manifest["tree_identity_sha256"] = "c" * 64
    unsigned = {key: value for key, value in manifest.items() if key != "fingerprint"}
    manifest["fingerprint"] = hashlib.sha256(canonical_json(unsigned)).hexdigest()
    files["manifest.json"] = canonical_json(manifest)
    files["SHA256SUMS"] = "".join(
        f"{hashlib.sha256(files[name]).hexdigest()}  {name}\n"
        for name in sorted(name for name in files if name != "SHA256SUMS")
    ).encode()
    with zipfile.ZipFile(bad_sha, "w") as target:
        for name, payload in files.items():
            target.writestr(name, payload)
    with pytest.raises(ValueError, match="tree identity SHA-256"):
        validate_identity_archive(bad_sha)

    leaked = archive(tmp_path / "leaked.zip", evidence(github_job_identity="source_canary.py"))
    with pytest.raises(ValueError, match="leakage"):
        validate_identity_archive(leaked)

    output = tmp_path / "existing.json"
    output.write_text("{}\n")
    with pytest.raises(ValueError, match="contradictory"):
        import_identity_archive(source, output)


def test_archive_structure_attacks_fail_closed(tmp_path: Path) -> None:
    valid = archive(tmp_path / "valid.zip")
    with zipfile.ZipFile(valid) as source:
        files = {name: source.read(name) for name in source.namelist()}

    traversal = tmp_path / "traversal.zip"
    with zipfile.ZipFile(traversal, "w") as target:
        for name, payload in files.items():
            target.writestr(name, payload)
        target.writestr("../source.py", b"source_canary")
    with pytest.raises(ValueError, match="missing or extra|unsafe"):
        validate_identity_archive(traversal)

    duplicate = tmp_path / "duplicate.zip"
    with zipfile.ZipFile(duplicate, "w") as target:
        for name, payload in files.items():
            target.writestr(name, payload)
        target.writestr("manifest.json", files["manifest.json"])
    with pytest.raises(ValueError, match="duplicate"):
        validate_identity_archive(duplicate)

    symlink = tmp_path / "symlink.zip"
    with zipfile.ZipFile(symlink, "w") as target:
        for name, payload in files.items():
            info = zipfile.ZipInfo(name)
            if name == "manifest.json":
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
            target.writestr(info, payload)
    with pytest.raises(ValueError, match="unsafe"):
        validate_identity_archive(symlink)


def test_archive_resource_attacks_fail_closed(tmp_path: Path) -> None:
    oversized = tmp_path / "oversized.zip"
    with zipfile.ZipFile(oversized, "w") as target:
        for name in ("cleanup-summary.json", "manifest.json", "tree-identity.json"):
            target.writestr(name, b"{}\n")
        target.writestr("SHA256SUMS", b"x" * 65_537)
    with pytest.raises(ValueError, match="oversized"):
        validate_identity_archive(oversized)

    ratio = tmp_path / "ratio.zip"
    with zipfile.ZipFile(ratio, "w", zipfile.ZIP_DEFLATED) as target:
        for name in ("cleanup-summary.json", "manifest.json", "tree-identity.json"):
            target.writestr(name, b"{}\n")
        target.writestr("SHA256SUMS", b"x" * 60_000)
    with pytest.raises(ValueError, match="compression ratio"):
        validate_identity_archive(ratio)


def test_workflow_is_manual_hardened_and_source_free(repository_root: Path) -> None:
    source = (repository_root / ".github/workflows/v2-01b-tree-identity.yml").read_text()
    workflow = yaml.safe_load(source)
    assert set(workflow[True]) == {"workflow_dispatch"}
    assert workflow["permissions"] == {"contents": "read"}
    for required in (
        "ubuntu-24.04",
        "persist-credentials: false",
        AUTHORIZED_REPOSITORY,
        AUTHORIZED_REVISION,
        'GIT_TERMINAL_PROMPT: "0"',
        'GIT_LFS_SKIP_SMUDGE: "1"',
        "protocol.file.allow=never",
        "ls-tree -r -z",
        "if: always()",
        "archguard-v2-01b-pysnooper2-tree-identity-${{ github.run_id }}",
    ):
        assert required in source
    assert "secrets." not in source
    assert "git checkout" not in source and "git worktree add" not in source


def test_readiness_remains_blocked_without_import(repository_root: Path) -> None:
    readiness = json.loads(
        (repository_root / "research/v2/readiness/micro-pilot-readiness.json").read_text()
    )
    assert readiness["V2_MICRO_PILOT_READY"] is False
    assert readiness["blocker_codes"] == ["PYSNOOPER_2_FIXED_TREE_IDENTITY_RECHECK_REQUIRED"]
    assert not (
        repository_root / "research/v2/evidence/pysnooper-2-fixed-tree-identity.json"
    ).exists()
