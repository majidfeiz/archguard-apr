"""Canonical tracked-record validation for Phase 12.8E."""

import json
from pathlib import Path
from typing import Any

from archguard.domain.canonical import canonical_json
from archguard.domain.orchestration import fingerprint
from archguard.domain.phase128e import (
    CANDIDATE_SCHEMA,
    LICENSE_SCHEMA,
    POLICY_SCHEMA,
    reject_outcome_fields,
)
from archguard.infrastructure.json_codec import unique_object


def load_record(path: Path, schema: str) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw, object_pairs_hook=unique_object)
    if not isinstance(value, dict) or canonical_json(value) != raw:
        raise ValueError("noncanonical Phase 12.8E record")
    if value.get("schema") != schema:
        raise ValueError("unexpected Phase 12.8E schema")
    supplied = value.get("fingerprint")
    body = {key: item for key, item in value.items() if key != "fingerprint"}
    if supplied != fingerprint(body):
        raise ValueError("Phase 12.8E fingerprint mismatch")
    reject_outcome_fields(value)
    return value


def validate_tracked_records(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    licenses = load_record(root / "research/licenses/license-registry-v1.json", LICENSE_SCHEMA)
    candidates = load_record(root / "research/candidates/candidate-pool-v1.json", CANDIDATE_SCHEMA)
    policy = load_record(root / "research/candidates/selection-policy-v1.json", POLICY_SCHEMA)
    if (
        candidates.get("phase_13_ready") is not False
        or candidates.get("final_pilot_list_frozen") is not False
    ):
        raise ValueError("Phase 12.8E cannot assert Phase 13 readiness or freeze the pilot")
    if candidates.get("selection_policy_fingerprint") != policy.get("fingerprint"):
        raise ValueError("selection policy binding mismatch")
    if candidates.get("license_registry_fingerprint") != licenses.get("fingerprint"):
        raise ValueError("license registry binding mismatch")
    return licenses, candidates, policy
