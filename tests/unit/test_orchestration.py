from dataclasses import replace
from pathlib import Path

import pytest

from archguard.application.services.orchestration import DeterministicCoordinator, replay, resume
from archguard.domain.orchestration import (
    AGENT_REQUEST_SCHEMA,
    AGENT_RESPONSE_SCHEMA,
    RUN_SPEC_SCHEMA,
    ActionType,
    AgentRequest,
    AgentResponse,
    AgentRole,
    ArtifactReference,
    Budget,
    CandidateEvidence,
    CandidateState,
    Disposition,
    EventKind,
    HumanDecision,
    HumanDecisionKind,
    ProposedAction,
    RepairRunSpec,
    RunState,
    Usage,
    append_event,
    rank_candidates,
    require_transition,
    validate_event_chain,
    validate_response,
    verify_checkpoint,
)
from archguard.infrastructure.orchestration import LocalRunArtifacts, ScriptedAgent


def ref(kind: str = "artifact", value: str = "1") -> ArtifactReference:
    return ArtifactReference(kind, value * 64)


def budget(**changes: int) -> Budget:
    values = dict(
        steps=20,
        invocations=10,
        candidates=5,
        validations=5,
        retries=2,
        input_units=100,
        output_units=100,
        total_units=300,
    )
    values.update(changes)
    return Budget(**values)


def spec(**changes: object) -> RepairRunSpec:
    values = dict(
        schema=RUN_SPEC_SCHEMA,
        run_id="run-1",
        baseline_commit="a" * 40,
        architecture_profile=ref("profile", "1"),
        repository_graph=ref("graph", "2"),
        execution_plan=ref("plan", "3"),
        roles=tuple(AgentRole),
        budget=budget(),
        deterministic_seed=7,
        human_approval_required=False,
    )
    values.update(changes)
    return RepairRunSpec(**values)  # type: ignore[arg-type]


def candidate(
    candidate_id: str, sha: str, *, valid: bool = True, fixed: int = 1, size: int = 10
) -> CandidateEvidence:
    return CandidateEvidence(
        candidate_id,
        ref("patch", sha),
        CandidateState.VALIDATED if valid else CandidateState.ARCHITECTURE_REJECTED,
        valid,
        valid,
        True,
        0,
        fixed,
        0,
        0,
        size,
        1,
        () if valid else ("architecture_rejection",),
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"schema": "bad"},
        {"roles": tuple(AgentRole) + (AgentRole.COORDINATOR,)},
        {"roles": (AgentRole.COORDINATOR,)},
        {"architecture_validation_required": False},
        {"execution_validation_required": False},
        {"baseline_commit": "bad"},
    ],
)
def test_run_spec_rejects_invalid(changes: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        spec(**changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"steps": -1},
        {"invocations": 1_000_001},
        {"total_units": 100},
    ],
)
def test_budget_rejects_invalid(changes: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        budget(**changes)


def test_budget_consumption_is_bounded() -> None:
    assert budget().consume(invocations=1).invocations == 9
    with pytest.raises(ValueError, match="budget exhausted"):
        budget().consume(invocations=11)


def test_run_transitions_and_terminal_state() -> None:
    require_transition(RunState.CREATED, RunState.ANALYZING)
    with pytest.raises(ValueError, match="illegal"):
        require_transition(RunState.CREATED, RunState.COMPLETED)
    with pytest.raises(ValueError, match="terminal"):
        require_transition(RunState.COMPLETED, RunState.FAILED)


def test_candidate_lifecycle_and_evidence_gate() -> None:
    value = CandidateEvidence(
        "c", ref("patch"), CandidateState.PROPOSED, False, False, False, 0, 0, 0, 0, 1, 1
    )
    assert value.transition(CandidateState.REGISTERED).state == CandidateState.REGISTERED
    with pytest.raises(ValueError):
        value.transition(CandidateState.SELECTED)
    with pytest.raises(ValueError, match="mandatory evidence"):
        replace(value, state=CandidateState.VALIDATED)


def test_agent_capabilities_and_response_security() -> None:
    request = AgentRequest(
        AGENT_REQUEST_SCHEMA,
        "run",
        "step",
        AgentRole.PATCH_PROPOSER,
        "submit",
        (),
        budget(),
        (ActionType.SUBMIT_CANDIDATE,),
    )
    response = AgentResponse(
        AGENT_RESPONSE_SCHEMA,
        AgentRole.PATCH_PROPOSER,
        Disposition.ACCEPTED,
        (),
        (),
        (),
        (),
        99,
        Usage(1, 1),
    )
    validate_response(request, response)
    with pytest.raises(ValueError, match="role escalation"):
        validate_response(request, replace(response, role=AgentRole.COORDINATOR))
    with pytest.raises(ValueError, match="prohibited"):
        validate_response(
            request, replace(response, actions=(ProposedAction(ActionType.SKIP_VALIDATION),))
        )
    with pytest.raises(ValueError, match="illegal capability"):
        replace(request, role=AgentRole.CONTEXT_ANALYST)


def test_sensitive_access_is_denied_without_capability() -> None:
    with pytest.raises(ValueError, match="sensitive"):
        AgentRequest(
            AGENT_REQUEST_SCHEMA,
            "run",
            "step",
            AgentRole.CONTEXT_ANALYST,
            "context",
            (ArtifactReference("bundle", "1" * 64, "source_sensitive"),),
            budget(),
            (ActionType.REQUEST_CONTEXT,),
            True,
        )


def test_event_chain_detects_removed_reordered_and_cross_run() -> None:
    events = append_event((), EventKind.RUN_CREATED, "run")
    events = append_event(events, EventKind.AGENT_REQUESTED, "run")
    assert validate_event_chain(events, "run") == events[-1].event_fingerprint
    with pytest.raises(ValueError):
        validate_event_chain(events[1:], "run")
    with pytest.raises(ValueError):
        validate_event_chain(tuple(reversed(events)), "run")
    with pytest.raises(ValueError, match="cross-run"):
        validate_event_chain(events, "other")


def test_deterministic_ranking_and_duplicate_detection() -> None:
    first = candidate("b", "2", fixed=1, size=20)
    second = candidate("a", "1", fixed=2, size=30)
    assert rank_candidates((first, second)) == rank_candidates((second, first))
    assert rank_candidates((first, second))[0].candidate_id == "a"
    with pytest.raises(ValueError, match="duplicate"):
        rank_candidates((first, replace(first, candidate_id="duplicate")))


def test_successful_flow_checkpoint_replay_resume_and_human_gate() -> None:
    value = spec(human_approval_required=True)
    coordinator = DeterministicCoordinator()
    snapshot, events = coordinator.create(value)
    for state in (
        RunState.ANALYZING,
        RunState.RETRIEVING_CONTEXT,
        RunState.PLANNING,
        RunState.REQUESTING_CANDIDATES,
    ):
        snapshot, events = coordinator.transition(value, snapshot, events, state)
    snapshot, events = coordinator.register_candidate(
        value, snapshot, events, "candidate", ref("patch")
    )
    snapshot, events = coordinator.transition(
        value, snapshot, events, RunState.VALIDATING_CANDIDATES
    )
    snapshot, events = coordinator.record_validation(
        value, snapshot, events, candidate("candidate", "1")
    )
    snapshot, events = coordinator.transition(value, snapshot, events, RunState.RANKING)
    snapshot, events = coordinator.rank(value, snapshot, events)
    assert snapshot.state == RunState.AWAITING_HUMAN_APPROVAL
    checkpoint = coordinator.checkpoint(value, snapshot, events)
    assert resume(value, events, checkpoint) == snapshot
    assert replay(value, events) == snapshot.state
    decision = HumanDecision(
        "archguard.human-decision/v1",
        value.run_id,
        "candidate",
        checkpoint.checkpoint_fingerprint,
        HumanDecisionKind.APPROVE,
    )
    snapshot, events = coordinator.decide(value, snapshot, events, decision, checkpoint)
    assert snapshot.state == RunState.COMPLETED


def test_duplicate_candidate_is_idempotent_and_not_charged() -> None:
    coordinator = DeterministicCoordinator()
    value = spec()
    snapshot, events = coordinator.create(value)
    snapshot, events = coordinator.register_candidate(value, snapshot, events, "one", ref("patch"))
    repeated, repeated_events = coordinator.register_candidate(
        value, snapshot, events, "two", ref("patch")
    )
    assert repeated == snapshot and repeated_events == events


def test_agent_invocation_charges_rejected_response_and_exhaustion() -> None:
    value = spec()
    coordinator = DeterministicCoordinator()
    snapshot, events = coordinator.create(value)
    request = AgentRequest(
        AGENT_REQUEST_SCHEMA,
        value.run_id,
        "s",
        AgentRole.REPAIR_PLANNER,
        "plan",
        (),
        snapshot.budget,
        (ActionType.PROPOSE_PLAN,),
    )
    bad = AgentResponse(
        AGENT_RESPONSE_SCHEMA,
        AgentRole.CONTEXT_ANALYST,
        Disposition.ACCEPTED,
        (),
        (),
        (),
        (),
        100,
        Usage(1, 2),
    )
    updated, events = coordinator.invoke(value, snapshot, events, ScriptedAgent((bad,)), request)
    assert updated.budget.invocations == snapshot.budget.invocations - 1
    assert events[-1].kind == EventKind.AGENT_REJECTED
    exhausted = replace(snapshot, budget=replace(snapshot.budget, invocations=0))
    exhausted, _ = coordinator.invoke(value, exhausted, events, ScriptedAgent((bad,)), request)
    assert exhausted.state == RunState.BUDGET_EXHAUSTED


def test_checkpoint_integrity_and_canonical_persistence(tmp_path: Path) -> None:
    value = spec()
    coordinator = DeterministicCoordinator()
    snapshot, events = coordinator.create(value)
    checkpoint = coordinator.checkpoint(value, snapshot, events)
    verify_checkpoint(checkpoint, value, events)
    with pytest.raises(ValueError, match="stale"):
        verify_checkpoint(
            replace(checkpoint, last_sequence=99, checkpoint_fingerprint=""), value, events
        )
    directory = tmp_path / "run"
    artifacts = LocalRunArtifacts()
    artifacts.write_run(directory, value, events, checkpoint)
    assert artifacts.read_run(directory) == (value, events, checkpoint)
    with pytest.raises(FileExistsError):
        artifacts.write_run(directory, value, events, checkpoint)
