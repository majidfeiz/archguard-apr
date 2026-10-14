"""Strict import of the reviewed, source-free Phase 13 final evidence bundle."""

import hashlib
import json
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from archguard.domain.canonical import canonical_json
from archguard.domain.orchestration import fingerprint
from archguard.domain.phase13_results import aggregate_phase13_results

ARCHIVE_SHA256 = "48080661ddbff3e486d47cebc63754e29d4dd4664febbb7f8143484e4c03e99d"
DIAGNOSTIC_FINGERPRINT = "71f60e3969313f139c493cad31ee20640fd6c2870d70411debdd5ab1956994e1"
POPULATION_FINGERPRINT = "421f3129ef6bee5883c41d05f087d6faff5b2a3de3b2ea543b4d27ade1488886"
PROTOCOL_FINGERPRINT = "eae1920ce71c025d2d94096798daf8b14df098249743631efe9a0aa7a541fbe8"
PROVIDER_FINGERPRINT = "f5dc6fb5b8bf54c7cf1b58b990fa3db44073500df9903e3a7d93cbeb1ad92c2d"
MEMBERS = frozenset(
    {
        "home/runner/work/_temp/provider-preflight.json",
        "home/runner/work/_temp/checkpoint.json",
        "tmp/archguard-phase13-cost-state.json",
        "tmp/archguard-phase13-evidence/cleanup.json",
        "tmp/archguard-phase13-evidence/cost-state.json",
        "tmp/archguard-phase13-evidence/execution-1.json",
        "tmp/archguard-phase13-evidence/execution-2.json",
        "tmp/archguard-phase13-evidence/execution-3.json",
        "tmp/archguard-phase13-evidence/execution-4.json",
        "tmp/archguard-phase13-evidence/manifest.json",
        "tmp/archguard-phase13-evidence/pre-provider-failure.json",
    }
)


def import_final_evidence(archive: Path) -> dict[str, Any]:
    raw = archive.read_bytes()
    if hashlib.sha256(raw).hexdigest() != ARCHIVE_SHA256:
        raise ValueError("final Phase 13 archive identity mismatch")
    values: dict[str, dict[str, Any]] = {}
    with zipfile.ZipFile(archive) as bundle:
        infos = bundle.infolist()
        if len(infos) != len(MEMBERS) or {item.filename for item in infos} != MEMBERS:
            raise ValueError("final Phase 13 archive members mismatch")
        for info in infos:
            path = PurePosixPath(info.filename)
            if path.is_absolute() or ".." in path.parts or stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError("unsafe final Phase 13 archive member")
            value = json.loads(bundle.read(info))
            if not isinstance(value, dict):
                raise ValueError("invalid final Phase 13 JSON member")
            values[info.filename] = value

    executions = [
        values[f"tmp/archguard-phase13-evidence/execution-{ordinal}.json"]
        for ordinal in range(1, 5)
    ]
    manifest = values["tmp/archguard-phase13-evidence/manifest.json"]
    cost = values["tmp/archguard-phase13-evidence/cost-state.json"]
    diagnostic = values["tmp/archguard-phase13-evidence/pre-provider-failure.json"]
    cleanup = values["tmp/archguard-phase13-evidence/cleanup.json"]
    result_hashes = [
        hashlib.sha256(
            canonical_json({key: value for key, value in item.items() if key != "provider_call_id"})
        ).hexdigest()
        for item in executions
    ]
    if (
        manifest.get("completed_executions") != 4
        or manifest.get("attrition") != 2
        or manifest.get("result_fingerprints") != result_hashes
        or manifest.get("population_fingerprint") != POPULATION_FINGERPRINT
        or manifest.get("protocol_fingerprint") != PROTOCOL_FINGERPRINT
        or manifest.get("provider_configuration_fingerprint") != PROVIDER_FINGERPRINT
        or cost.get("provider_calls_completed") != 4
        or cost.get("observed_usd") != "0.1296325"
        or cost.get("reserved_usd") != "0"
        or cost.get("remaining_internal_budget_usd") != "4.3703675"
        or cleanup != {"complete": True, "schema": "archguard.phase-13-cleanup/v1"}
        or diagnostic.get("stage") != "checkout"
        or diagnostic.get("exception_category") != "validation_failure"
        or diagnostic.get("diagnostic_fingerprint") != DIAGNOSTIC_FINGERPRINT
    ):
        raise ValueError("final Phase 13 evidence invariant mismatch")
    aggregate = aggregate_phase13_results(executions)
    imported: dict[str, Any] = {
        "schema": "archguard.phase-13-final-import/v1",
        "archive_sha256": ARCHIVE_SHA256,
        "manifest": manifest,
        "cost_state": cost,
        "cleanup": cleanup,
        "executions": executions,
        "attrition_diagnostic": diagnostic,
        "aggregate": aggregate,
    }
    imported["import_fingerprint"] = fingerprint(imported)
    return imported
