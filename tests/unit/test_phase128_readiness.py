import hashlib
import io
import json
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from archguard.domain.readiness import (
    DECISION_SCHEMA,
    HumanDecision,
    HumanDecisionRecord,
    readiness_report,
)
from archguard.infrastructure.phase127_evidence import (
    EXPECTED_FILES,
    as_json,
    validate_phase127_zip,
)

SHA = "a" * 64


def evidence_files() -> dict[str, str]:
    values = {name: "source-free=true\n" for name in EXPECTED_FILES}
    values.update(
        {
            "run-metadata.txt": (
                "schema=archguard.phase-12.7-x86-qualification/v1\n"
                f"archguard_commit={SHA}\nrunner_os=Linux\nhost_architecture=x86_64\n"
                "task=PySnooper-2\n"
                f"bugsinpy_revision={SHA}\nbuggy_revision={SHA}\nfixed_revision={SHA}\n"
            ),
            "archguard-version.txt": "0.12.6\n",
            "profile-status.txt": "profile_compilations=3\nprofile_byte_identical=true\n",
            "acquisition-proof.txt": (
                "framework_revision_verified=true\nbuggy_revision_verified=true\n"
                "fixed_revision_verified=true\ngold_material_uploaded=false\n"
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


def test_evidence_is_validated_and_canonical(tmp_path: Path) -> None:
    path = tmp_path / "evidence.zip"
    digest = make_zip(path, evidence_files())
    value = validate_phase127_zip(path, digest)
    assert value.evaluator == "QUALIFIED"
    assert as_json(value).endswith(b"\n")
    assert as_json(value) == as_json(replace(value, fingerprint=value.fingerprint))


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
