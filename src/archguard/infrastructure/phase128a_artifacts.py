"""Strict canonical readers for source-free Phase 12.8A artifacts."""

import json
from pathlib import Path
from typing import Any

from archguard.domain.orchestration import fingerprint
from archguard.infrastructure.artifact_io import read_artifact

EXPECTED = {
    "licenses/phase-12.8a-license-evidence.json": "archguard.license-evidence-registry/v1",
    "graph-evidence/pysnooper-2.pending.json": "archguard.architecture-graph-evidence/v1",
    "selection/phase-12.8a-candidates.json": "archguard.candidate-registry/v1",
    "pilots/phase-12.8a-plan.json": "archguard.qualification-pilot-plan/v1",
    "power/phase-12.8a-power-design.json": "archguard.power-design-analysis/v1",
    "protocol/confirmatory-protocol-v2-proposed.json": (
        "archguard.confirmatory-protocol/v2-proposed"
    ),
}


def validate_phase128a_artifacts(root: Path) -> dict[str, Any]:
    results: list[dict[str, str]] = []
    for relative, schema in sorted(EXPECTED.items()):
        path = root / relative
        raw = read_artifact(path, None, 1024 * 1024)
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict) or value.get("schema") != schema:
            raise ValueError("invalid Phase 12.8A artifact schema")
        claimed = value.pop("fingerprint", None)
        actual = fingerprint(value)
        if claimed != actual:
            raise ValueError("Phase 12.8A artifact fingerprint mismatch")
        results.append({"path": relative, "fingerprint": actual})
    return {"status": "valid", "artifact_count": len(results), "artifacts": results}
