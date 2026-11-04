"""Strict JSON loading and immutable canonical persistence for V2 preflight."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from archguard.domain.canonical import canonical_json
from archguard.domain.v2_preflight import V2PreflightManifest, V2PreflightResult
from archguard.infrastructure.json_codec import unique_object

FIELDS = {
    "schema",
    "project_id",
    "task_id",
    "project_revision",
    "task_revision",
    "candidate_registry_fingerprint",
    "architecture_profile_fingerprint",
    "evaluator_fingerprint",
    "failure_signature_fingerprint",
    "dependency_lock_fingerprint",
    "checkout_tree_fingerprint",
    "checks",
    "timeout_seconds",
    "memory_mib",
    "cpu_limit",
    "disk_mib",
}


def load_v2_preflight_manifest(path: Path) -> V2PreflightManifest:
    raw = path.read_bytes()
    if len(raw) > 128 * 1024:
        raise ValueError("preflight manifest too large")
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError("invalid preflight fields")
    data: dict[str, Any] = value
    checks = data["checks"]
    if not isinstance(checks, dict) or not all(
        isinstance(key, str) and isinstance(item, bool) for key, item in checks.items()
    ):
        raise ValueError("invalid preflight checks")
    data = {**data, "checks": tuple(sorted(checks.items()))}
    return V2PreflightManifest(**data)


def write_v2_preflight_result(path: Path, result: V2PreflightResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(canonical_json(asdict(result)))
