import hashlib
import json
import stat
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from archguard.domain.canonical import canonical_json
from archguard.entrypoints.cli.app import app
from archguard.infrastructure.v2_capability_freeze import (
    CAPABILITY_FINGERPRINT,
    EXPECTED_JSON_SHA256,
    CapabilityArtifactIdentity,
    import_capability_evidence,
    validate_capability_artifact,
)
from archguard.infrastructure.v2_evidence import validate_source_free
from archguard.infrastructure.v2_protocol import load_frozen_protocol

pytestmark = pytest.mark.unit


def _archive(path: Path, payload: bytes, name: str = "v2-provider-capability-probe.json") -> bytes:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        info = zipfile.ZipInfo(name, (2026, 11, 28, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = (stat.S_IFREG | 0o444) << 16
        archive.writestr(info, payload)
    return path.read_bytes()


def _identity(archive: bytes) -> CapabilityArtifactIdentity:
    return CapabilityArtifactIdentity(zip_sha256=hashlib.sha256(archive).hexdigest())


def test_capability_archive_import_is_exact_and_idempotent(
    repository_root: Path, tmp_path: Path
) -> None:
    payload = (repository_root / "research/v2/evidence/provider-capability-probe.json").read_bytes()
    archive_path = tmp_path / "capability.zip"
    archive = _archive(archive_path, payload)
    identity = _identity(archive)
    assert validate_capability_artifact(archive_path, identity) == payload
    destination = tmp_path / "imported.json"
    import_capability_evidence(archive_path, destination, identity)
    import_capability_evidence(archive_path, destination, identity)
    assert destination.read_bytes() == payload
    assert hashlib.sha256(payload).hexdigest() == EXPECTED_JSON_SHA256


def test_capability_archive_rejects_tampering_and_nonflat_members(
    repository_root: Path, tmp_path: Path
) -> None:
    payload = (repository_root / "research/v2/evidence/provider-capability-probe.json").read_bytes()
    archive_path = tmp_path / "capability.zip"
    archive = _archive(archive_path, payload)
    with pytest.raises(ValueError, match="ZIP hash mismatch"):
        validate_capability_artifact(
            archive_path,
            CapabilityArtifactIdentity(zip_sha256="0" * 64),
        )
    nested_path = tmp_path / "nested.zip"
    nested = _archive(nested_path, payload, "nested/v2-provider-capability-probe.json")
    with pytest.raises(ValueError, match="exactly one allowed member"):
        validate_capability_artifact(nested_path, _identity(nested))
    destination = tmp_path / "existing.json"
    destination.write_bytes(b"{}\n")
    with pytest.raises(ValueError, match="contradicts"):
        import_capability_evidence(archive_path, destination, _identity(archive))


def test_frozen_capability_and_amendment_bindings(repository_root: Path) -> None:
    evidence_path = repository_root / "research/v2/evidence/provider-capability-probe.json"
    evidence = json.loads(evidence_path.read_bytes())
    validate_source_free(evidence)
    assert hashlib.sha256(evidence_path.read_bytes()).hexdigest() == EXPECTED_JSON_SHA256
    assert evidence["diagnostic_fingerprint"] == CAPABILITY_FINGERPRINT
    assert evidence["accepted_provider_calls"] == 1
    assert evidence["scientific_executions"] == 0
    assert evidence["observed_cost_usd"] == "0.0014825"
    assert evidence["patch_semantics_valid"] is False

    protocol = load_frozen_protocol(repository_root)
    assert protocol.fingerprint == (
        "5a110f57dc86e1b4e932bf81e5905a71da65253ab93ed2b68f323f16bd681e05"
    )
    assert protocol.readiness_fingerprint == (
        "f7313d942ac8053d0f93f39ed6ddce74eb873603fea88c401bff25f453eb90f6"
    )
    for relative in (
        "research/v2/evidence/provider-capability-provenance.json",
        "research/v2/protocol/micro-pilot-amendment-v3.json",
        "research/v2/readiness/amended-micro-pilot-readiness.json",
    ):
        value = json.loads((repository_root / relative).read_bytes())
        fingerprint = value.pop("fingerprint")
        assert fingerprint == hashlib.sha256(canonical_json(value)).hexdigest()


def test_capability_import_cli_does_not_accept_wrong_archive(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "wrong.zip"
    archive.write_bytes(b"not the authorized artifact")
    destination = tmp_path / "evidence.json"
    result = CliRunner().invoke(
        app,
        [
            "v2-micro-pilot",
            "capability-freeze-import",
            str(archive),
            "--destination",
            str(destination),
        ],
    )
    assert result.exit_code != 0
    assert not destination.exists()
