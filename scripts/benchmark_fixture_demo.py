"""Offline Phase 11 dry-run over controlled benchmark-shaped metadata fixtures."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from archguard.application.services.benchmark import assert_agent_visible, evaluate_eligibility
from archguard.domain.benchmark import EligibilityEvidence

FIXTURES = {
    "synthetic": {"task_id": "synthetic-001", "problem_statement": "Return the expected value."},
    "bugsinpy-compatible": {
        "task_id": "bugsinpy-shape-001",
        "problem_statement": "A public failing test identifies a regression.",
        "buggy_revision": "a" * 40,
    },
    "swe-bench-compatible": {
        "task_id": "swe-bench-shape-001",
        "problem_statement": "A public issue describes incorrect behavior.",
        "base_commit": "b" * 40,
    },
}


def run(kind: str) -> dict[str, object]:
    visible = FIXTURES[kind]
    assert_agent_visible(visible, ("ARCHGUARD_GOLD_CANARY",))
    evidence = EligibilityEvidence(
        task_id=str(visible["task_id"]),
        source_available=True,
        revision_available=True,
        licensed=True,
        environment_ready=True,
        target_failure_reproduced=True,
        deterministic_baseline=True,
        architecture_analyzed=True,
        graph_constructed=True,
        evaluator_ready=True,
        gold_isolated=True,
        supported_platform=True,
        no_external_service=True,
        within_resources=True,
    )
    eligibility = evaluate_eligibility(evidence)
    return {
        "fixture": kind,
        "external_benchmark_verified": False,
        "network_access": False,
        "agent_visible_fields": sorted(visible),
        "eligibility": asdict(eligibility),
        "status": "fixture_verified",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", choices=sorted(FIXTURES), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = json.dumps(run(args.fixture), sort_keys=True, separators=(",", ":")) + "\n"
    args.output.write_text(payload, encoding="utf-8")


if __name__ == "__main__":
    main()
