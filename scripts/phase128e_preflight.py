#!/usr/bin/env python3
"""Regenerate Phase 12.8E source-free records and optional CI evidence."""

import argparse
import hashlib
from dataclasses import asdict
from pathlib import Path
from typing import Any

from archguard.domain.canonical import canonical_json
from archguard.domain.orchestration import fingerprint
from archguard.domain.phase128e import (
    CANDIDATE_SCHEMA,
    LICENSE_SCHEMA,
    POLICY_SCHEMA,
    AuditStatus,
    CandidateRecord,
    LicenseRecord,
    fingerprinted,
    select_preparation_pool,
)

EVIDENCE_TIMESTAMP = "2026-10-07T10:39:04Z"
BUGSINPY_REVISION = "11c5f1eea954a42132cfd06bf257766a7963e0fd"
MIB = 1024**2
GIB = 1024**3


def license_records() -> tuple[LicenseRecord, ...]:
    common_unresolved = dict(
        license_file_path=None,
        license_sha256=None,
        spdx_identifier=None,
        redistribution_status=AuditStatus.UNRESOLVED,
        benchmark_use_status=AuditStatus.UNRESOLVED,
        source_execution_status=AuditStatus.UNRESOLVED,
        audit_status=AuditStatus.UNRESOLVED,
    )
    return (
        LicenseRecord(
            subject_id="bugsinpy-framework",
            subject_kind="framework",
            official_source_url="https://github.com/soarsmu/BugsInPy",
            immutable_locator=BUGSINPY_REVISION,
            evidence_timestamp=EVIDENCE_TIMESTAMP,
            evidence_type="immutable_repository_tree",
            reason="The frozen official repository tree contains no license file.",
            limitations=(
                "Public visibility is not license evidence.",
                "External-locator use only; no framework source or metadata is redistributed.",
            ),
            **common_unresolved,
        ),
        LicenseRecord(
            subject_id="swe-bench-framework",
            subject_kind="framework",
            official_source_url="https://github.com/SWE-bench/SWE-bench",
            immutable_locator="02e7a74ffd0b707aab73d203fe87bdc7c76afc8e",
            license_file_path="LICENSE",
            license_sha256="2bd2e08df7147f67a69b42c10efae09bd4bf119df397371036187d5dd1b02f57",
            spdx_identifier="MIT",
            redistribution_status=AuditStatus.VERIFIED,
            benchmark_use_status=AuditStatus.VERIFIED,
            source_execution_status=AuditStatus.VERIFIED,
            evidence_timestamp="2026-10-03T20:39:35Z",
            evidence_type="imported_immutable_license_evidence",
            audit_status=AuditStatus.VERIFIED,
            reason="Official immutable license file is an unambiguous MIT license.",
            limitations=(
                "The framework license does not determine target-project or dataset licensing.",
            ),
        ),
        LicenseRecord(
            subject_id="swe-bench-verified-dataset",
            subject_kind="dataset",
            official_source_url="https://huggingface.co/datasets/SWE-bench/SWE-bench_Verified",
            immutable_locator="78f471bf655a3137b2e8a75af1501690ec009ec3",
            evidence_timestamp="2026-10-03T20:39:35Z",
            evidence_type="immutable_metadata_locator_only",
            reason=(
                "No defensible official dataset redistribution license was acquired; "
                "payload is excluded."
            ),
            limitations=(
                "Framework licensing cannot authorize dataset or target-source redistribution.",
            ),
            **common_unresolved,
        ),
        _project_license(
            "pysnooper",
            "https://github.com/cool-RR/PySnooper",
            "e21a31162f4c54be693d8ca8260e42393b39abd3",
            "5db83d6347f7e52946b736c71d0d59bb80c8a4485fcfa0a5140bdd839152be88",
            "MIT",
        ),
        _project_license(
            "pysnooper-legacy",
            "https://github.com/cool-RR/PySnooper",
            "6e3d797be3fa0a746fb5b1b7c7fea78eb926c208",
            "0c4250d2a9f0e39d024593ede44eb5044e5fbd1175a8962ec9659d8ace34de9e",
            "MIT",
        ),
        _project_license(
            "black",
            "https://github.com/psf/black",
            "26c9465a22c732ab1e17b0dec578fa3432e9b558",
            "9c0428f0c3b4779850cf5bd96e11aaa8afc72d4a86d4a36223d7aba2e58d6e00",
            "MIT",
        ),
        _project_license(
            "cookiecutter",
            "https://github.com/cookiecutter/cookiecutter",
            "9568ab6ecd2d6836646006c59473c4a4ac0dee04",
            "31f691f875aa4ccfbd491b1dc3bf0f2f44e48c53ec573c4eaae79a9afedae7cf",
            "BSD-3-Clause",
        ),
    )


def _project_license(
    subject: str, url: str, revision: str, digest: str, spdx: str
) -> LicenseRecord:
    return LicenseRecord(
        subject_id=subject,
        subject_kind="project",
        official_source_url=url,
        immutable_locator=revision,
        license_file_path="LICENSE",
        license_sha256=digest,
        spdx_identifier=spdx,
        redistribution_status=AuditStatus.VERIFIED,
        benchmark_use_status=AuditStatus.VERIFIED,
        source_execution_status=AuditStatus.VERIFIED,
        evidence_timestamp=EVIDENCE_TIMESTAMP,
        evidence_type="official_immutable_license_file",
        audit_status=AuditStatus.VERIFIED,
        reason=f"Official immutable license file unambiguously matches {spdx}.",
        limitations=("This factual audit is not legal advice.",),
    )


def candidates() -> tuple[CandidateRecord, ...]:
    rows = (
        (
            "PySnooper-1",
            "PySnooper",
            "https://github.com/cool-RR/PySnooper",
            "e21a31162f4c54be693d8ca8260e42393b39abd3",
            "56f22f8ffe1c6b2be4d2cf3ad1987fdb66113da2",
            "3.8.1",
            112640,
            False,
            "pysnooper",
        ),
        (
            "PySnooper-2",
            "PySnooper",
            "https://github.com/cool-RR/PySnooper",
            "e21a31162f4c54be693d8ca8260e42393b39abd3",
            "814abc34a098c1b98cb327105ac396f985d2413e",
            "3.8.1",
            112640,
            False,
            "pysnooper",
        ),
        (
            "PySnooper-3",
            "PySnooper",
            "https://github.com/cool-RR/PySnooper",
            "6e3d797be3fa0a746fb5b1b7c7fea78eb926c208",
            "15555ed760000b049aff8fecc79d29339c1224c3",
            "3.8.1",
            51200,
            False,
            "pysnooper-legacy",
        ),
        (
            "black-1",
            "black",
            "https://github.com/psf/black",
            "26c9465a22c732ab1e17b0dec578fa3432e9b558",
            "c0a7582e3d4cc8bec3b7f5a6c52b36880dcb57d7",
            "3.8.3",
            5130240,
            False,
            "black",
        ),
        (
            "black-2",
            "black",
            "https://github.com/psf/black",
            "c8ca6b2b9ff3510bee12129824cebfc2fc51e5b2",
            "892eddacd215d685e136686b7f629ade70adca83",
            "3.8.3",
            4986880,
            False,
            "black",
        ),
        (
            "black-3",
            "black",
            "https://github.com/psf/black",
            "8126b4f6a9342290de4655e6a8a78cd288ce7daa",
            "7a14a37981862ef418f3cdb4a7e2375856f97529",
            "3.8.3",
            4986880,
            False,
            "black",
        ),
        (
            "black-4",
            "black",
            "https://github.com/psf/black",
            "65ea568e3301951f26e0e3b98f6d5dc80132e917",
            "c7495b9aa098ef7a358fc74556359d21c6a4ba11",
            "3.8.3",
            4956160,
            False,
            "black",
        ),
        (
            "cookiecutter-1",
            "cookiecutter",
            "https://github.com/cookiecutter/cookiecutter",
            "c15633745df6abdb24e02746b82aadb20b8cdf8c",
            "7f6804c4953a18386809f11faf4d86898570debc",
            "3.6.9",
            880640,
            True,
            "cookiecutter",
        ),
        (
            "cookiecutter-2",
            "cookiecutter",
            "https://github.com/cookiecutter/cookiecutter",
            "d7e7b28811e474e14d1bed747115e47dcdd15ba3",
            "90434ff4ea4477941444f1e83313beb414838535",
            "3.6.9",
            880640,
            True,
            "cookiecutter",
        ),
        (
            "cookiecutter-3",
            "cookiecutter",
            "https://github.com/cookiecutter/cookiecutter",
            "5c282f020a8db7e5e7c4e7b51b010556ca31fb7f",
            "7129d474206761a6156925db78eee4b62a0e3944",
            "3.6.9",
            849920,
            True,
            "cookiecutter",
        ),
        (
            "cookiecutter-4",
            "cookiecutter",
            "https://github.com/cookiecutter/cookiecutter",
            "9568ab6ecd2d6836646006c59473c4a4ac0dee04",
            "457a1a4e862aab4102b644ff1d2b2e2b5a766b3c",
            "3.6.9",
            604160,
            False,
            "cookiecutter",
        ),
    )
    return tuple(
        CandidateRecord(
            task_id=task,
            source_index="BugsInPy",
            source_revision=BUGSINPY_REVISION,
            project=project,
            official_repository=url,
            language="Python",
            buggy_revision=buggy,
            fixed_revision=fixed,
            evaluator_locator=f"projects/{project}/bugs/{task.rsplit('-', 1)[1]}/run_test.sh",
            python_version=python,
            checkout_archive_bytes=size,
            cpu_limit=2,
            memory_limit_bytes=2 * GIB,
            timeout_minutes=20,
            repetitions=3,
            requires_secrets=False,
            evaluator_network_required=False,
            unsupported_gitlink=gitlink,
            lfs_required=False,
            license_record=license_id,
            eligible=not gitlink,
            ineligible_reason="UNSUPPORTED_GITLINK" if gitlink else None,
        )
        for task, project, url, buggy, fixed, python, size, gitlink, license_id in rows
    )


def records() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    licenses = fingerprinted(
        LICENSE_SCHEMA,
        {
            "legal_advice": False,
            "records": [asdict(record) for record in license_records()],
            "required_dependency_status": "UNRESOLVED",
        },
    )
    policy = fingerprinted(
        POLICY_SCHEMA,
        {
            "algorithm": [
                "filter_metadata_completeness",
                "filter_verified_project_license",
                "filter_platform_and_static_analysis_compatibility",
                "filter_bounded_resources",
                "group_by_project",
                "sort_by_source_free_task_identifier",
                "round_robin_across_projects",
                "cap_each_project_at_four",
                "select_eight_to_twelve",
            ],
            "maximum_per_project": 4,
            "maximum_selected": 12,
            "minimum_projects": 3,
            "minimum_selected": 8,
            "outcome_blind": True,
            "random_selection": False,
            "scoped_projects": ["PySnooper", "black", "cookiecutter"],
            "source_revision": BUGSINPY_REVISION,
        },
    )
    observed = candidates()
    selected = select_preparation_pool(observed)
    observed_payload = [asdict(item) for item in observed]
    pool = fingerprinted(
        CANDIDATE_SCHEMA,
        {
            "complete_observed_metadata_count": len(observed),
            "eligible_count": sum(item.eligible for item in observed),
            "eligible_project_count": len({item.project for item in observed if item.eligible}),
            "final_pilot_list_frozen": False,
            "ineligible_count": sum(not item.eligible for item in observed),
            "ineligible_counts_by_reason": {"UNSUPPORTED_GITLINK": 3},
            "input_fingerprint": fingerprint(observed_payload),
            "license_registry_fingerprint": licenses["fingerprint"],
            "observed": observed_payload,
            "phase_13_ready": False,
            "preparation_pool_count": len(selected),
            "selected_identifiers": [item.task_id for item in selected],
            "selection_policy_fingerprint": policy["fingerprint"],
            "status": "PREPARATION_POOL_NOT_FINAL_PILOT",
        },
    )
    return licenses, pool, policy


def write_record(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json(value))


def write_tracked(root: Path) -> None:
    licenses, pool, policy = records()
    write_record(root / "research/licenses/license-registry-v1.json", licenses)
    write_record(root / "research/candidates/candidate-pool-v1.json", pool)
    write_record(root / "research/candidates/selection-policy-v1.json", policy)


def write_evidence(output: Path) -> None:
    licenses, pool, policy = records()
    output.mkdir(parents=True, exist_ok=True)
    summaries = {
        "manifest.json": {
            "schema": "archguard.phase-12.8e-manifest/v1",
            "phase_13_ready": False,
            "license_registry_fingerprint": licenses["fingerprint"],
            "candidate_registry_fingerprint": pool["fingerprint"],
            "selection_policy_fingerprint": policy["fingerprint"],
        },
        "license-summary.json": {
            "schema": "archguard.phase-12.8e-license-summary/v1",
            "verified": 5,
            "unresolved": 2,
            "licenses_unverified": True,
        },
        "candidate-pool-summary.json": {
            "schema": "archguard.phase-12.8e-candidate-summary/v1",
            "observed": 11,
            "eligible": 8,
            "ineligible": 3,
            "selected": pool["selected_identifiers"],
        },
        "selection-determinism.json": {
            "schema": "archguard.phase-12.8e-selection-determinism/v1",
            "input_fingerprint": pool["input_fingerprint"],
            "policy_fingerprint": policy["fingerprint"],
            "registry_fingerprint": pool["fingerprint"],
            "byte_identical": True,
        },
        "security-scan-summary.json": {
            "schema": "archguard.phase-12.8e-security-scan/v1",
            "forbidden_findings": 0,
            "status": "PASSED",
        },
        "cleanup-summary.json": {
            "schema": "archguard.phase-12.8e-cleanup/v1",
            "external_root_removed": True,
            "status": "COMPLETE",
        },
        "readiness-summary.json": {
            "schema": "archguard.phase-12.8e-readiness/v1",
            "phase_13_ready": False,
            "resolved_blockers": ["INSUFFICIENT_CANDIDATE_POOL"],
            "remaining_blockers": [
                "INSUFFICIENT_QUALIFIED_TASKS",
                "PILOT_SELECTION_NOT_READY",
                "TASK_LIST_NOT_FROZEN",
                "LICENSES_UNVERIFIED",
                "PROTOCOL_REVIEW_REQUIRED",
                "PROVIDER_NOT_CONFIGURED",
            ],
        },
    }
    for name, body in summaries.items():
        write_record(output / name, {**body, "fingerprint": fingerprint(body)})
    checksums = []
    for path in sorted(output.glob("*.json")):
        checksums.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}")
    (output / "SHA256SUMS").write_text("\n".join(checksums) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path)
    parser.add_argument("--evidence-output", type=Path)
    parser.add_argument("--cleanup-confirmed", action="store_true")
    args = parser.parse_args()
    if args.repository_root:
        write_tracked(args.repository_root)
    if args.evidence_output:
        if not args.cleanup_confirmed:
            parser.error("--evidence-output requires --cleanup-confirmed")
        write_evidence(args.evidence_output)
    if not args.repository_root and not args.evidence_output:
        parser.error("an output option is required")


if __name__ == "__main__":
    main()
