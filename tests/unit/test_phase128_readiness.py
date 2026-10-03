import hashlib
import io
import json
import stat
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from archguard.domain.readiness import (
    DECISION_SCHEMA,
    HumanDecision,
    HumanDecisionRecord,
    docker_sha256_digest,
    git_sha1_commit,
    readiness_report,
    sha256_digest,
)
from archguard.infrastructure.phase127_evidence import (
    EXPECTED_ARCHGUARD_COMMIT,
    EXPECTED_BUGGY_REVISION,
    EXPECTED_FILES,
    EXPECTED_FIXED_REVISION,
    EXPECTED_FRAMEWORK_REVISION,
    as_json,
    validate_phase127_zip,
)

SHA = "a" * 64
DOCKER_SHA = f"sha256:{SHA}"


def evidence_files() -> dict[str, str]:
    values = {name: "source-free=true\n" for name in EXPECTED_FILES}
    values.update(
        {
            "run-metadata.txt": (
                "schema=archguard.phase-12.7-x86-qualification/v1\n"
                f"archguard_commit={EXPECTED_ARCHGUARD_COMMIT}\n"
                "runner_os=Linux\nhost_architecture=x86_64\n"
                "task=PySnooper-2\n"
                f"bugsinpy_revision={EXPECTED_FRAMEWORK_REVISION}\n"
                f"buggy_revision={EXPECTED_BUGGY_REVISION}\n"
                f"fixed_revision={EXPECTED_FIXED_REVISION}\n"
            ),
            "archguard-version.txt": "0.12.6\n",
            "profile-status.txt": "profile_compilations=3\nprofile_byte_identical=true\n",
            "acquisition-proof.txt": (
                "framework_revision_verified=true\nbuggy_revision_verified=true\n"
                f"fixed_revision_verified=true\nlicense_file_sha256={SHA}\n"
                "gold_material_uploaded=false\n"
            ),
            "profile-sha256.txt": f"{SHA}  pysnooper-profile.json\n",
            "evaluator-image.txt": (
                f"evaluator_image_id={DOCKER_SHA}\nevaluator_image_architecture=amd64\n"
            ),
            "buggy-run-signatures.txt": "".join(
                f"run={number} signature_sha256={SHA}\n" for number in range(1, 4)
            ),
            "buggy-baseline-summary.txt": "classification=STABLE\nexpected_failure_runs=3\n",
            "fixed-control-summary.txt": "trusted_fixed_control=PASSED\nevaluator=QUALIFIED\n",
            "cleanup-and-quarantine.txt": (
                "remaining_phase_12_7_containers=0\nuploaded_source_files=0\n"
                "uploaded_patch_files=0\nuploaded_raw_evaluator_logs=0\n"
            ),
            "conclusion.txt": "platform_gate=PASSED\n",
        }
    )
    return values


def make_zip(path: Path, values: dict[str, str], extra: tuple[str, str] | None = None) -> str:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in values.items():
            archive.writestr(name, value)
        if extra:
            archive.writestr(*extra)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_zip_with_member(
    path: Path,
    member: str,
    payload: bytes,
    *,
    mode: int = stat.S_IFREG | 0o600,
    compression: int = zipfile.ZIP_STORED,
) -> str:
    with zipfile.ZipFile(path, "w") as archive:
        for name, value in evidence_files().items():
            info = zipfile.ZipInfo(name)
            info.external_attr = (mode if name == member else stat.S_IFREG | 0o600) << 16
            info.compress_type = compression if name == member else zipfile.ZIP_STORED
            archive.writestr(info, payload if name == member else value.encode())
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_evidence_is_validated_and_canonical(tmp_path: Path) -> None:
    path = tmp_path / "evidence.zip"
    digest = make_zip(path, evidence_files())
    value = validate_phase127_zip(path, digest)
    assert value.evaluator == "QUALIFIED"
    assert as_json(value).endswith(b"\n")
    assert as_json(value) == as_json(replace(value, fingerprint=value.fingerprint))


@pytest.mark.parametrize(
    "revision",
    [
        EXPECTED_ARCHGUARD_COMMIT,
        EXPECTED_FRAMEWORK_REVISION,
        EXPECTED_BUGGY_REVISION,
        EXPECTED_FIXED_REVISION,
    ],
)
def test_full_lowercase_git_sha1_commit_is_accepted(revision: str) -> None:
    assert git_sha1_commit(revision) == revision


@pytest.mark.parametrize(
    "revision",
    [
        "a" * 7,
        "a" * 39,
        "a" * 41,
        "A" * 40,
        "g" * 40,
        " a" + "a" * 39,
        "a" * 40 + " ",
        "a" * 64,
    ],
)
def test_invalid_git_sha1_commit_is_rejected(revision: str) -> None:
    with pytest.raises(ValueError, match="Git SHA-1"):
        git_sha1_commit(revision)


@pytest.mark.parametrize("value", [SHA, "0" * 64])
def test_raw_sha256_digest_is_accepted(value: str) -> None:
    assert sha256_digest(value) == value


@pytest.mark.parametrize(
    "value", ["a" * 40, "a" * 63, "a" * 65, "A" * 64, f"sha256:{SHA}", f" {SHA}"]
)
def test_invalid_raw_sha256_digest_is_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        sha256_digest(value)


def test_docker_sha256_digest_has_distinct_semantics() -> None:
    assert docker_sha256_digest(DOCKER_SHA) == DOCKER_SHA
    for invalid in (SHA, "sha256:" + "a" * 63, "SHA256:" + SHA, DOCKER_SHA + " "):
        with pytest.raises(ValueError, match="Docker SHA-256"):
            docker_sha256_digest(invalid)


@pytest.mark.parametrize("name", ["../escape", "/absolute", "unexpected.txt", "café.txt"])
def test_evidence_rejects_unexpected_and_unsafe_names(tmp_path: Path, name: str) -> None:
    path = tmp_path / "bad.zip"
    digest = make_zip(path, evidence_files(), (name, "bad"))
    with pytest.raises(ValueError):
        validate_phase127_zip(path, digest)


def test_evidence_rejects_duplicate_member(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.zip"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, value in evidence_files().items():
            archive.writestr(name, value)
        archive.writestr("conclusion.txt", "platform_gate=PASSED\n")
    path.write_bytes(buffer.getvalue())
    with pytest.raises(ValueError, match="duplicate"):
        validate_phase127_zip(path, hashlib.sha256(path.read_bytes()).hexdigest())


@pytest.mark.parametrize("mode", [stat.S_IFLNK | 0o777, stat.S_IFCHR | 0o600])
def test_evidence_rejects_symlink_and_device_members(tmp_path: Path, mode: int) -> None:
    path = tmp_path / "special.zip"
    digest = make_zip_with_member(path, "environment.txt", b"target", mode=mode)
    with pytest.raises(ValueError, match="file type"):
        validate_phase127_zip(path, digest)


def test_evidence_rejects_directory_member(tmp_path: Path) -> None:
    path = tmp_path / "directory.zip"
    digest = make_zip(path, evidence_files(), ("unexpected/", ""))
    with pytest.raises(ValueError, match="layout"):
        validate_phase127_zip(path, digest)


def test_evidence_rejects_oversized_member(tmp_path: Path) -> None:
    path = tmp_path / "large.zip"
    digest = make_zip_with_member(path, "environment.txt", b"a" * (1024 * 1024 + 1))
    with pytest.raises(ValueError, match="too large"):
        validate_phase127_zip(path, digest)


def test_evidence_rejects_high_compression_ratio(tmp_path: Path) -> None:
    path = tmp_path / "ratio.zip"
    digest = make_zip_with_member(
        path,
        "environment.txt",
        b"a" * (1024 * 1024),
        compression=zipfile.ZIP_DEFLATED,
    )
    with pytest.raises(ValueError, match="compression ratio"):
        validate_phase127_zip(path, digest)


def test_evidence_rejects_non_utf8_member(tmp_path: Path) -> None:
    path = tmp_path / "encoding.zip"
    digest = make_zip_with_member(path, "environment.txt", b"\xff\xfe")
    with pytest.raises(ValueError, match="invalid evidence ZIP"):
        validate_phase127_zip(path, digest)


def test_evidence_rejects_tampering_and_contradiction(tmp_path: Path) -> None:
    path = tmp_path / "tampered.zip"
    values = evidence_files()
    values["fixed-control-summary.txt"] = "trusted_fixed_control=FAILED\nevaluator=QUALIFIED\n"
    digest = make_zip(path, values)
    with pytest.raises(ValueError):
        validate_phase127_zip(path, digest)
    with pytest.raises(ValueError, match="SHA-256"):
        validate_phase127_zip(path, "b" * 64)


def test_pending_decision_cannot_approve() -> None:
    decision = HumanDecisionRecord(
        schema=DECISION_SCHEMA,
        subject_kind="confirmatory_protocol",
        reviewed_fingerprint=SHA,
        reviewer_name="",
        review_timestamp="",
        decision=HumanDecision.PENDING,
        checklist={"protocol_read": False},
        comments="",
    )
    assert not decision.approves(SHA)


def test_fake_or_stale_approval_is_rejected() -> None:
    with pytest.raises(ValueError):
        HumanDecisionRecord(
            DECISION_SCHEMA,
            "architecture_profile",
            SHA,
            "",
            "",
            HumanDecision.APPROVE,
            {"profile_read": True},
            "",
        )
    decision = HumanDecisionRecord(
        DECISION_SCHEMA,
        "architecture_profile",
        SHA,
        "Human Reviewer",
        "2026-10-03T12:00:00Z",
        HumanDecision.APPROVE,
        {"profile_read": True},
        "reviewed",
    )
    assert decision.approves(SHA)
    assert not decision.approves("b" * 64)


def test_readiness_fails_closed_and_is_deterministic() -> None:
    facts = {"qualified_stable_tasks": 0, "qualified_projects": 0}
    first = readiness_report(facts)
    assert not first["phase_13_ready"]
    assert "PHASE_12_7_EVIDENCE_MISSING" in first["blocker_codes"]
    assert json.dumps(first, sort_keys=True) == json.dumps(readiness_report(facts), sort_keys=True)


def test_readiness_requires_every_gate() -> None:
    facts = {
        "phase_12_7_evidence": True,
        "qualified_stable_tasks": 4,
        "qualified_projects": 2,
        "candidate_pool_count": 20,
        "selected_pilot_tasks": 4,
        "graph_evidence_validated": True,
        "task_list_frozen": True,
        "licenses_verified": True,
        "evaluators_qualified": True,
        "linux_x86_evidence": True,
        "architecture_analysis_complete": True,
        "profiles_frozen": True,
        "protocol_frozen": True,
        "provider_decision_recorded": True,
    }
    assert readiness_report(facts)["phase_13_ready"]
