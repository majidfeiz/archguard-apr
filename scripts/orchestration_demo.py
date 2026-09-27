"""Deterministic Phase 8 mechanism demonstration; no repository or provider access."""

import argparse
import hashlib
import json
from dataclasses import replace
from pathlib import Path

from archguard.application.services.orchestration import DeterministicCoordinator, replay, resume
from archguard.domain.orchestration import (
    CandidateEvidence,
    CandidateState,
    HumanDecision,
    HumanDecisionKind,
    RepairRunSpec,
    RunState,
)
from archguard.infrastructure.orchestration import LocalRunArtifacts


def run(spec: RepairRunSpec, output: Path) -> dict[str, object]:
    coordinator = DeterministicCoordinator()
    snapshot, events = coordinator.create(spec)
    for state in (
        RunState.ANALYZING,
        RunState.RETRIEVING_CONTEXT,
        RunState.PLANNING,
        RunState.REQUESTING_CANDIDATES,
    ):
        snapshot, events = coordinator.transition(spec, snapshot, events, state)
    rejected_patch = replace(spec.repository_graph, kind="patch", sha256="1" * 64)
    accepted_patch = replace(spec.repository_graph, kind="patch", sha256="2" * 64)
    snapshot, events = coordinator.register_candidate(
        spec, snapshot, events, "candidate-rejected", rejected_patch
    )
    snapshot, events = coordinator.register_candidate(
        spec, snapshot, events, "candidate-valid", accepted_patch
    )
    snapshot, events = coordinator.transition(
        spec, snapshot, events, RunState.VALIDATING_CANDIDATES
    )
    rejected = CandidateEvidence(
        "candidate-rejected",
        rejected_patch,
        CandidateState.ARCHITECTURE_REJECTED,
        False,
        False,
        True,
        0,
        0,
        1,
        0,
        120,
        1,
        ("architecture_rejection",),
    )
    accepted = CandidateEvidence(
        "candidate-valid",
        accepted_patch,
        CandidateState.VALIDATED,
        True,
        True,
        True,
        0,
        1,
        0,
        0,
        100,
        1,
    )
    snapshot, events = coordinator.record_validation(spec, snapshot, events, rejected)
    snapshot, events = coordinator.record_validation(spec, snapshot, events, accepted)
    snapshot, events = coordinator.transition(spec, snapshot, events, RunState.RANKING)
    snapshot, events = coordinator.rank(spec, snapshot, events)
    approval_checkpoint = coordinator.checkpoint(spec, snapshot, events)
    decision = HumanDecision(
        "archguard.human-decision/v1",
        spec.run_id,
        "candidate-valid",
        approval_checkpoint.checkpoint_fingerprint,
        HumanDecisionKind.APPROVE,
    )
    snapshot, events = coordinator.decide(spec, snapshot, events, decision, approval_checkpoint)
    checkpoint = coordinator.checkpoint(spec, snapshot, events)
    assert replay(spec, events) == RunState.COMPLETED
    assert resume(spec, events, checkpoint) == snapshot
    LocalRunArtifacts().write_run(output, spec, events, checkpoint)
    hashes = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(output.iterdir())
    }
    return {
        "state": snapshot.state,
        "selected_candidate_id": snapshot.selected_candidate_id,
        "event_count": len(events),
        "artifact_sha256": hashes,
        "replay_agent_invocations": 0,
        "replay_executions": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    spec = LocalRunArtifacts().load_spec(args.spec)
    print(json.dumps(run(spec, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
