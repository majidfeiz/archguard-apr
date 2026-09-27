"""Deterministic coordinator and side-effect-free replay."""

from dataclasses import dataclass, replace

from archguard.application.ports.orchestration import AgentPort
from archguard.domain.orchestration import (
    AGENT_REQUEST_SCHEMA,
    CHECKPOINT_SCHEMA,
    ActionType,
    AgentRequest,
    AgentRole,
    ArtifactReference,
    Budget,
    CandidateEvidence,
    CandidateState,
    Disposition,
    EventKind,
    HumanDecision,
    HumanDecisionKind,
    RepairCheckpoint,
    RepairRunSpec,
    RunEvent,
    RunState,
    append_event,
    rank_candidates,
    require_transition,
    validate_event_chain,
    validate_response,
    verify_checkpoint,
)


@dataclass(frozen=True)
class RunSnapshot:
    state: RunState
    budget: Budget
    candidates: tuple[CandidateEvidence, ...]
    selected_candidate_id: str | None = None
    pending_human_decision: bool = False


class DeterministicCoordinator:
    def create(self, spec: RepairRunSpec) -> tuple[RunSnapshot, tuple[RunEvent, ...]]:
        events = append_event(
            (), EventKind.RUN_CREATED, spec.run_id, (("spec_fingerprint", spec.spec_fingerprint),)
        )
        return RunSnapshot(RunState.CREATED, spec.budget, ()), events

    def transition(
        self,
        spec: RepairRunSpec,
        snapshot: RunSnapshot,
        events: tuple[RunEvent, ...],
        target: RunState,
    ) -> tuple[RunSnapshot, tuple[RunEvent, ...]]:
        require_transition(snapshot.state, target)
        updated = replace(snapshot, state=target)
        return updated, append_event(
            events,
            EventKind.STATE_TRANSITION,
            spec.run_id,
            (("from", snapshot.state), ("to", target)),
        )

    def invoke(
        self,
        spec: RepairRunSpec,
        snapshot: RunSnapshot,
        events: tuple[RunEvent, ...],
        agent: AgentPort,
        request: AgentRequest,
    ) -> tuple[RunSnapshot, tuple[RunEvent, ...]]:
        if snapshot.budget.invocations == 0:
            return self.transition(spec, snapshot, events, RunState.BUDGET_EXHAUSTED)
        charged = snapshot.budget.consume(invocations=1)
        events = append_event(
            events,
            EventKind.AGENT_REQUESTED,
            spec.run_id,
            (("role", request.role), ("step_id", request.step_id)),
        )
        response = agent.invoke(request)
        charged = charged.consume(
            input_units=response.usage.input_units,
            output_units=response.usage.output_units,
            total_units=response.usage.input_units + response.usage.output_units,
        )
        updated = replace(snapshot, budget=charged)
        events = append_event(
            events, EventKind.BUDGET_CONSUMED, spec.run_id, (("step_id", request.step_id),)
        )
        try:
            validate_response(request, response)
        except ValueError:
            return updated, append_event(
                events, EventKind.AGENT_REJECTED, spec.run_id, (("step_id", request.step_id),)
            )
        kind = (
            EventKind.AGENT_ACCEPTED
            if response.disposition == Disposition.ACCEPTED
            else EventKind.AGENT_REJECTED
        )
        return updated, append_event(events, kind, spec.run_id, (("step_id", request.step_id),))

    def register_candidate(
        self,
        spec: RepairRunSpec,
        snapshot: RunSnapshot,
        events: tuple[RunEvent, ...],
        candidate_id: str,
        patch: ArtifactReference,
    ) -> tuple[RunSnapshot, tuple[RunEvent, ...]]:
        if any(item.patch.sha256 == patch.sha256 for item in snapshot.candidates):
            return snapshot, events
        budget = snapshot.budget.consume(candidates=1)
        candidate = CandidateEvidence(
            candidate_id, patch, CandidateState.REGISTERED, False, False, False, 0, 0, 0, 0, 0, 0
        )
        updated = replace(snapshot, budget=budget, candidates=(*snapshot.candidates, candidate))
        return updated, append_event(
            events,
            EventKind.CANDIDATE_REGISTERED,
            spec.run_id,
            (("candidate_id", candidate_id), ("patch", patch.sha256)),
        )

    def record_validation(
        self,
        spec: RepairRunSpec,
        snapshot: RunSnapshot,
        events: tuple[RunEvent, ...],
        evidence: CandidateEvidence,
    ) -> tuple[RunSnapshot, tuple[RunEvent, ...]]:
        budget = snapshot.budget.consume(validations=1)
        candidates = tuple(
            evidence if item.candidate_id == evidence.candidate_id else item
            for item in snapshot.candidates
        )
        check_found = any(
            item.candidate_id == evidence.candidate_id for item in snapshot.candidates
        )
        if not check_found:
            raise ValueError("unknown candidate")
        kind = (
            EventKind.CANDIDATE_VALIDATED
            if evidence.state == CandidateState.VALIDATED
            else EventKind.CANDIDATE_REJECTED
        )
        return replace(snapshot, budget=budget, candidates=candidates), append_event(
            events, kind, spec.run_id, (("candidate_id", evidence.candidate_id),)
        )

    def rank(
        self, spec: RepairRunSpec, snapshot: RunSnapshot, events: tuple[RunEvent, ...]
    ) -> tuple[RunSnapshot, tuple[RunEvent, ...]]:
        ranked = rank_candidates(snapshot.candidates)
        selected = next(
            (item.candidate_id for item in ranked if item.state == CandidateState.VALIDATED), None
        )
        if selected is None:
            updated, events = self.transition(spec, snapshot, events, RunState.REJECTED)
            return updated, events
        ranked_values = tuple(
            replace(item, state=CandidateState.RANKED)
            if item.state == CandidateState.VALIDATED
            else item
            for item in ranked
        )
        updated = replace(
            snapshot,
            candidates=ranked_values,
            selected_candidate_id=selected,
            pending_human_decision=spec.human_approval_required,
        )
        events = append_event(
            events, EventKind.RANKING_COMPLETED, spec.run_id, (("selected_candidate_id", selected),)
        )
        target = (
            RunState.AWAITING_HUMAN_APPROVAL if spec.human_approval_required else RunState.COMPLETED
        )
        return self.transition(spec, updated, events, target)

    def decide(
        self,
        spec: RepairRunSpec,
        snapshot: RunSnapshot,
        events: tuple[RunEvent, ...],
        decision: HumanDecision,
        checkpoint: RepairCheckpoint,
    ) -> tuple[RunSnapshot, tuple[RunEvent, ...]]:
        if (
            decision.run_id != spec.run_id
            or decision.candidate_id != snapshot.selected_candidate_id
        ):
            raise ValueError("stale human decision")
        if decision.checkpoint_fingerprint != checkpoint.checkpoint_fingerprint:
            raise ValueError("stale human decision checkpoint")
        events = append_event(
            events, EventKind.HUMAN_DECISION, spec.run_id, (("decision", decision.decision),)
        )
        target = {
            HumanDecisionKind.APPROVE: RunState.COMPLETED,
            HumanDecisionKind.REJECT: RunState.REJECTED,
            HumanDecisionKind.REVISE: RunState.REQUESTING_CANDIDATES,
            HumanDecisionKind.CANCEL: RunState.CANCELLED,
        }[decision.decision]
        return self.transition(
            spec, replace(snapshot, pending_human_decision=False), events, target
        )

    def checkpoint(
        self, spec: RepairRunSpec, snapshot: RunSnapshot, events: tuple[RunEvent, ...]
    ) -> RepairCheckpoint:
        chain = validate_event_chain(events, spec.run_id)
        return RepairCheckpoint(
            CHECKPOINT_SCHEMA,
            spec.run_id,
            spec.spec_fingerprint,
            snapshot.state,
            len(events) - 1,
            chain,
            snapshot.budget,
            snapshot.candidates,
            snapshot.selected_candidate_id,
            snapshot.pending_human_decision,
        )


def replay(spec: RepairRunSpec, events: tuple[RunEvent, ...]) -> RunState:
    """Rebuild state without agents, repositories, patches, or execution."""
    validate_event_chain(events, spec.run_id)
    state = RunState.CREATED
    for event in events:
        if event.kind == EventKind.STATE_TRANSITION:
            payload = dict(event.payload)
            check = RunState(payload["from"])
            if check != state:
                raise ValueError("event transition source mismatch")
            target = RunState(payload["to"])
            require_transition(state, target)
            state = target
    return state


def resume(
    spec: RepairRunSpec, events: tuple[RunEvent, ...], checkpoint: RepairCheckpoint
) -> RunSnapshot:
    verify_checkpoint(checkpoint, spec, events)
    if replay(spec, events) != checkpoint.state:
        raise ValueError("checkpoint semantic state mismatch")
    return RunSnapshot(
        checkpoint.state,
        checkpoint.remaining_budget,
        checkpoint.candidates,
        checkpoint.selected_candidate_id,
        checkpoint.pending_human_decision,
    )


def request(
    spec: RepairRunSpec,
    snapshot: RunSnapshot,
    role: AgentRole,
    step_id: str,
    task_type: str,
    actions: tuple[ActionType, ...],
    artifacts: tuple[ArtifactReference, ...] = (),
) -> AgentRequest:
    return AgentRequest(
        AGENT_REQUEST_SCHEMA,
        spec.run_id,
        step_id,
        role,
        task_type,
        artifacts,
        snapshot.budget,
        actions,
    )
