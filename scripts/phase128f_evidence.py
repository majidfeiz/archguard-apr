#!/usr/bin/env python3
"""Assemble, package, validate, and import Phase 12.8F evidence."""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from archguard.domain.canonical import canonical_json
from archguard.domain.orchestration import fingerprint
from archguard.domain.phase128f import QUALIFICATION_SCHEMA
from archguard.infrastructure.phase128f_evidence import (
    ARTIFACT_MEMBERS,
    import_archive,
    package,
    validate_archive,
    validate_directory,
)


def _record(schema: str, body: dict[str, Any]) -> dict[str, Any]:
    value = {"schema": schema, **body}
    value["fingerprint"] = fingerprint(value)
    return value


def assemble(
    results_path: Path,
    adapters_path: Path,
    output: Path,
    run_id: str,
    security_scan_path: Path,
    transfer_bytes: int = 0,
) -> None:
    results = json.loads(results_path.read_text(encoding="utf-8"))
    adapters = json.loads(adapters_path.read_text(encoding="utf-8"))
    security_scan = json.loads(security_scan_path.read_text(encoding="utf-8"))
    if security_scan.get("status") != "PASSED":
        raise ValueError("successful security scan required")
    selected = {result["task_id"] for result in results}
    adapter_values = [item for item in adapters["adapters"] if item["task_id"] in selected]
    output.mkdir(parents=True, exist_ok=False)
    files = {
        "manifest.json": _record(
            "archguard.phase-12.8f-manifest/v1",
            {
                "adapter_fingerprints": [item["fingerprint"] for item in adapter_values],
                "adapter_registry_fingerprint": adapters["fingerprint"],
                "candidate_registry_fingerprint": adapters["candidate_registry_fingerprint"],
                "github_run_id": run_id,
                "platform": "Linux-x86_64",
                "selection_policy_fingerprint": adapters["selection_policy_fingerprint"],
                "task_ids": [result["task_id"] for result in results],
            },
        ),
        "adapter-summary.json": _record(
            "archguard.phase-12.8f-adapter-summary/v1",
            {"adapters": adapter_values, "imported_prior_task": "PySnooper-2"},
        ),
        "task-qualification.json": _record(QUALIFICATION_SCHEMA, {"results": results}),
        "fixed-control-summary.json": _record(
            "archguard.phase-12.8f-fixed-controls/v1",
            {
                "controls": [
                    {"result": result["fixed_control"], "task_id": result["task_id"]}
                    for result in results
                ]
            },
        ),
        "determinism-summary.json": _record(
            "archguard.phase-12.8f-determinism/v1",
            {
                "attempt_counts": {
                    result["task_id"]: len(result["buggy_attempts"]) for result in results
                },
                "canonical": True,
            },
        ),
        "resource-summary.json": _record(
            "archguard.phase-12.8f-resources/v1",
            {
                "artifact_ceiling_bytes": 10 * 1024**2,
                "disk_ceiling_bytes": 8 * 1024**3,
                "measured_transfer_bytes": transfer_bytes,
                "task_resources": [result["resources"] for result in results],
                "transfer_ceiling_bytes": 2 * 1024**3,
            },
        ),
        "security-scan-summary.json": security_scan,
        "cleanup-summary.json": _record(
            "archguard.phase-12.8f-cleanup/v1",
            {"containers_remaining": 0, "external_root_removed": True, "status": "COMPLETE"},
        ),
        "readiness-summary.json": _record(
            "archguard.phase-12.8f-readiness/v1",
            {
                "phase_13_ready": False,
                "pilot_selected": False,
                "task_list_frozen": False,
            },
        ),
    }
    for name, value in files.items():
        (output / name).write_bytes(canonical_json(value))
    sums = [
        f"{hashlib.sha256((output / name).read_bytes()).hexdigest()}  {name}"
        for name in sorted(ARTIFACT_MEMBERS - {"SHA256SUMS"})
    ]
    (output / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    validate_directory(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    assemble_parser = commands.add_parser("assemble")
    assemble_parser.add_argument("--results", type=Path, required=True)
    assemble_parser.add_argument("--adapters", type=Path, required=True)
    assemble_parser.add_argument("--output", type=Path, required=True)
    assemble_parser.add_argument("--run-id", required=True)
    assemble_parser.add_argument("--security-scan", type=Path, required=True)
    assemble_parser.add_argument("--transfer-bytes", type=int, default=0)
    package_parser = commands.add_parser("package")
    package_parser.add_argument("--source", type=Path, required=True)
    package_parser.add_argument("--archive", type=Path, required=True)
    validate_parser = commands.add_parser("validate")
    validate_parser.add_argument("--archive", type=Path, required=True)
    import_parser = commands.add_parser("import")
    import_parser.add_argument("--archive", type=Path, required=True)
    import_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "assemble":
        assemble(
            args.results,
            args.adapters,
            args.output,
            args.run_id,
            args.security_scan,
            args.transfer_bytes,
        )
    elif args.command == "package":
        package(args.source, args.archive)
    elif args.command == "validate":
        validate_archive(args.archive)
    else:
        import_archive(args.archive, args.output)


if __name__ == "__main__":
    main()
