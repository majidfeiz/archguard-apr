import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_proposed_protocol_is_review_required_and_fair(repository_root: Path) -> None:
    value = json.loads(
        (repository_root / "research/v2/protocol/proposed-ablation-protocol.json").read_text()
    )
    assert value["status"] == "PROPOSED_REVIEW_REQUIRED"
    assert tuple(sorted(value["conditions"])) == (
        "BASELINE",
        "FULL_ARCHGUARD",
        "GRAPH_CONSTRAINTS",
        "GRAPH_ONLY",
    )
    assert value["population"]["minimum_qualified_tasks"] == 30
    assert value["population"]["preferred_qualified_tasks"] == 50
    assert value["population"]["minimum_projects"] == 3
    assert value["fairness"]["condition_specific_task_replacement"] is False
    assert all(
        item
        for key, item in value["fairness"].items()
        if key != "condition_specific_task_replacement"
    )


def test_cost_and_readiness_disable_provider_calls(repository_root: Path) -> None:
    cost = json.loads(
        (repository_root / "research/v2/cost/proposed-micro-pilot-cost-plan.json").read_text()
    )
    readiness = json.loads(
        (repository_root / "research/v2/readiness/v2-01-readiness.json").read_text()
    )
    assert cost["hard_ceiling"] == "1.00"
    assert cost["provider_calls_enabled"] is False
    assert cost["automatic_continuation"] is False
    assert readiness["provider_calls_executed"] == 0
    assert readiness["micro_pilot"]["ready"] is False


def test_synthetic_fixture_provenance_and_inventory(repository_root: Path) -> None:
    root = repository_root / "tests/fixtures/v2_patch"
    names = {path.name for path in root.iterdir()}
    assert {
        "valid.diff",
        "valid-fenced.txt",
        "valid-structured.json",
        "prose-only.txt",
        "empty-response.json",
        "multiple.txt",
        "malformed.diff",
        "truncated.diff",
        "path-traversal.diff",
        "absolute-path.diff",
        "symlink.diff",
        "rename.diff",
        "binary.diff",
        "no-op.diff",
        "context-mismatch.diff",
        "policy-rejection.diff",
        "architecture-rejection.diff",
    } <= names
    provenance = (root / "README.md").read_text()
    assert "no benchmark source" in provenance
    assert "no benchmark" not in b"".join(
        path.read_bytes() for path in root.iterdir() if path.suffix in {".diff", ".patch"}
    ).decode(errors="ignore")
