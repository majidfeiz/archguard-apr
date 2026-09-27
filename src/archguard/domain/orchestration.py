"""Provider-neutral, immutable repair orchestration contracts."""

import hashlib
import re
from dataclasses import asdict, dataclass, replace
from enum import StrEnum

from archguard.domain.canonical import canonical_json
from archguard.domain.repository import check, digest

RUN_SPEC_SCHEMA = "archguard.repair-run-spec/v1"
EVENT_LOG_SCHEMA = "archguard.repair-run-events/v1"
CHECKPOINT_SCHEMA = "archguard.repair-checkpoint/v1"
AGENT_REQUEST_SCHEMA = "archguard.agent-request/v1"
AGENT_RESPONSE_SCHEMA = "archguard.agent-response/v1"
HUMAN_DECISION_SCHEMA = "archguard.human-decision/v1"
ZERO_FINGERPRINT = "0" * 64


def fingerprint(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def valid_id(value: str) -> None:
    check(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value) is not None, "invalid ID")


class AgentRole(StrEnum):
    COORDINATOR = "coordinator"
    CONTEXT_ANALYST = "context_analyst"
    REPAIR_PLANNER = "repair_planner"
    PATCH_PROPOSER = "patch_proposer"
    ARCHITECTURE_REVIEWER = "architecture_reviewer"
    EXECUTION_REVIEWER = "execution_reviewer"
    CANDIDATE_RANKER = "candidate_ranker"
    HUMAN_GATE = "human_gate"


class Capability(StrEnum):
    REQUEST_CONTEXT = "request_context"
    PROPOSE_PLAN = "propose_plan"
    PROPOSE_PATCH = "propose_patch"
    REVIEW_ARCHITECTURE = "review_architecture"
    REVIEW_EXECUTION = "review_execution"
    RANK_CANDIDATES = "rank_candidates"
    RECORD_HUMAN_DECISION = "record_human_decision"
    READ_SENSITIVE = "read_sensitive"


ROLE_CAPABILITIES = {
    AgentRole.COORDINATOR: frozenset(),
    AgentRole.CONTEXT_ANALYST: frozenset({Capability.REQUEST_CONTEXT}),
    AgentRole.REPAIR_PLANNER: frozenset({Capability.PROPOSE_PLAN}),
    AgentRole.PATCH_PROPOSER: frozenset({Capability.PROPOSE_PATCH}),
    AgentRole.ARCHITECTURE_REVIEWER: frozenset({Capability.REVIEW_ARCHITECTURE}),
    AgentRole.EXECUTION_REVIEWER: frozenset({Capability.REVIEW_EXECUTION}),
    AgentRole.CANDIDATE_RANKER: frozenset({Capability.RANK_CANDIDATES}),
    AgentRole.HUMAN_GATE: frozenset({Capability.RECORD_HUMAN_DECISION}),
}


class RunState(StrEnum):
    CREATED = "created"
    ANALYZING = "analyzing"
    RETRIEVING_CONTEXT = "retrieving_context"
    PLANNING = "planning"
    REQUESTING_CANDIDATES = "requesting_candidates"
    VALIDATING_CANDIDATES = "validating_candidates"
    RANKING = "ranking"
    AWAITING_HUMAN_APPROVAL = "awaiting_human_approval"
    COMPLETED = "completed"
    REJECTED = "rejected"
    BUDGET_EXHAUSTED = "budget_exhausted"
    CANCELLED = "cancelled"
    FAILED = "failed"


TERMINAL_STATES = frozenset(
    {
        RunState.COMPLETED,
        RunState.REJECTED,
        RunState.BUDGET_EXHAUSTED,
        RunState.CANCELLED,
        RunState.FAILED,
    }
)
LEGAL_TRANSITIONS = {
    RunState.CREATED: frozenset({RunState.ANALYZING, RunState.CANCELLED}),
    RunState.ANALYZING: frozenset(
        {RunState.RETRIEVING_CONTEXT, RunState.FAILED, RunState.CANCELLED}
    ),
    RunState.RETRIEVING_CONTEXT: frozenset(
        {RunState.PLANNING, RunState.FAILED, RunState.CANCELLED}
    ),
    RunState.PLANNING: frozenset(
        {RunState.REQUESTING_CANDIDATES, RunState.FAILED, RunState.CANCELLED}
    ),
    RunState.REQUESTING_CANDIDATES: frozenset(
        {
            RunState.VALIDATING_CANDIDATES,
            RunState.REJECTED,
            RunState.BUDGET_EXHAUSTED,
            RunState.CANCELLED,
        }
    ),
    RunState.VALIDATING_CANDIDATES: frozenset(
        {
            RunState.RANKING,
            RunState.REJECTED,
            RunState.BUDGET_EXHAUSTED,
            RunState.FAILED,
            RunState.CANCELLED,
        }
    ),
    RunState.RANKING: frozenset(
        {
            RunState.AWAITING_HUMAN_APPROVAL,
            RunState.COMPLETED,
            RunState.REJECTED,
            RunState.FAILED,
            RunState.CANCELLED,
        }
    ),
    RunState.AWAITING_HUMAN_APPROVAL: frozenset(
        {RunState.COMPLETED, RunState.REJECTED, RunState.REQUESTING_CANDIDATES, RunState.CANCELLED}
    ),
}


def require_transition(current: RunState, target: RunState) -> None:
    check(current not in TERMINAL_STATES, "terminal state cannot transition")
    if target in {RunState.BUDGET_EXHAUSTED, RunState.CANCELLED}:
        return
    check(target in LEGAL_TRANSITIONS.get(current, frozenset()), "illegal run transition")


class CandidateState(StrEnum):
    PROPOSED = "proposed"
    REGISTERED = "registered"
    ARCHITECTURE_VALIDATING = "architecture_validating"
    ARCHITECTURE_REJECTED = "architecture_rejected"
    EXECUTION_VALIDATING = "execution_validating"
    FUNCTIONALLY_REJECTED = "functionally_rejected"
    VALIDATED = "validated"
    RANKED = "ranked"
    SELECTED = "selected"
    DISCARDED = "discarded"


CANDIDATE_TRANSITIONS = {
    CandidateState.PROPOSED: {CandidateState.REGISTERED},
    CandidateState.REGISTERED: {CandidateState.ARCHITECTURE_VALIDATING},
    CandidateState.ARCHITECTURE_VALIDATING: {
        CandidateState.ARCHITECTURE_REJECTED,
        CandidateState.EXECUTION_VALIDATING,
    },
    CandidateState.EXECUTION_VALIDATING: {
        CandidateState.FUNCTIONALLY_REJECTED,
        CandidateState.VALIDATED,
    },
    CandidateState.VALIDATED: {CandidateState.RANKED},
    CandidateState.RANKED: {CandidateState.SELECTED, CandidateState.DISCARDED},
}


@dataclass(frozen=True, order=True)
class ArtifactReference:
    kind: str
    sha256: str
    sensitivity: str = "source_free"

    def __post_init__(self) -> None:
        valid_id(self.kind)
        digest(self.sha256)
        check(
            self.sensitivity in {"source_free", "source_sensitive", "sensitive_log"},
            "invalid sensitivity",
        )


@dataclass(frozen=True)
class Budget:
    steps: int
    invocations: int
    candidates: int
    validations: int
    retries: int
    input_units: int
    output_units: int
    total_units: int

    def __post_init__(self) -> None:
        values = tuple(asdict(self).values())
        check(
            all(isinstance(value, int) and 0 <= value <= 1_000_000 for value in values),
            "invalid budget",
        )
        check(self.input_units + self.output_units <= self.total_units, "contradictory unit budget")

    def consume(self, **amounts: int) -> "Budget":
        values = asdict(self)
        for name, amount in amounts.items():
            check(name in values and 0 <= amount <= values[name], "budget exhausted")
            values[name] -= amount
        return Budget(**values)


@dataclass(frozen=True)
class RepairRunSpec:
    schema: str
    run_id: str
    baseline_commit: str
    architecture_profile: ArtifactReference
    repository_graph: ArtifactReference
    execution_plan: ArtifactReference
    roles: tuple[AgentRole, ...]
    budget: Budget
    deterministic_seed: int
    human_approval_required: bool
    architecture_validation_required: bool = True
    execution_validation_required: bool = True
    spec_fingerprint: str = ""

    def __post_init__(self) -> None:
        check(self.schema == RUN_SPEC_SCHEMA, "unsupported run specification schema")
        valid_id(self.run_id)
        check(
            re.fullmatch(r"[0-9a-f]{40}", self.baseline_commit) is not None,
            "invalid baseline commit",
        )
        object.__setattr__(self, "roles", tuple(self.roles))
        check(len(set(self.roles)) == len(self.roles), "duplicate role")
        check(set(self.roles) >= set(AgentRole), "missing required role")
        check(
            self.architecture_validation_required and self.execution_validation_required,
            "mandatory validation gate disabled",
        )
        check(0 <= self.deterministic_seed <= 2**63 - 1, "invalid deterministic seed")
        expected = fingerprint({k: v for k, v in asdict(self).items() if k != "spec_fingerprint"})
        if self.spec_fingerprint:
            check(self.spec_fingerprint == expected, "spec fingerprint mismatch")
        else:
            object.__setattr__(self, "spec_fingerprint", expected)


class ActionType(StrEnum):
    REQUEST_CONTEXT = "request_context"
    PROPOSE_PLAN = "propose_plan"
    SUBMIT_CANDIDATE = "submit_candidate"
    REVIEW_ARCHITECTURE = "review_architecture"
    REVIEW_EXECUTION = "review_execution"
    RANK = "rank"
    HUMAN_DECISION = "human_decision"
    SKIP_VALIDATION = "skip_validation"


ACTION_CAPABILITY = {
    ActionType.REQUEST_CONTEXT: Capability.REQUEST_CONTEXT,
    ActionType.PROPOSE_PLAN: Capability.PROPOSE_PLAN,
    ActionType.SUBMIT_CANDIDATE: Capability.PROPOSE_PATCH,
    ActionType.REVIEW_ARCHITECTURE: Capability.REVIEW_ARCHITECTURE,
    ActionType.REVIEW_EXECUTION: Capability.REVIEW_EXECUTION,
    ActionType.RANK: Capability.RANK_CANDIDATES,
    ActionType.HUMAN_DECISION: Capability.RECORD_HUMAN_DECISION,
}


@dataclass(frozen=True, order=True)
class ProposedAction:
    action: ActionType
    artifact: ArtifactReference | None = None


@dataclass(frozen=True)
class Usage:
    input_units: int
    output_units: int

    def __post_init__(self) -> None:
        check(
            0 <= self.input_units <= 1_000_000 and 0 <= self.output_units <= 1_000_000,
            "invalid usage",
        )


@dataclass(frozen=True)
class AgentRequest:
    schema: str
    run_id: str
    step_id: str
    role: AgentRole
    task_type: str
    artifacts: tuple[ArtifactReference, ...]
    remaining_budget: Budget
    allowed_actions: tuple[ActionType, ...]
    sensitive_access_acknowledged: bool = False

    def __post_init__(self) -> None:
        check(self.schema == AGENT_REQUEST_SCHEMA, "unsupported agent request schema")
        valid_id(self.run_id)
        valid_id(self.step_id)
        valid_id(self.task_type)
        object.__setattr__(self, "artifacts", tuple(sorted(self.artifacts)))
        object.__setattr__(self, "allowed_actions", tuple(sorted(set(self.allowed_actions))))
        allowed = ROLE_CAPABILITIES[self.role]
        check(
            all(ACTION_CAPABILITY.get(action) in allowed for action in self.allowed_actions),
            "illegal capability assignment",
        )
        if any(item.sensitivity != "source_free" for item in self.artifacts):
            check(
                Capability.READ_SENSITIVE in allowed and self.sensitive_access_acknowledged,
                "sensitive artifact access denied",
            )


class Disposition(StrEnum):
    ACCEPTED = "accepted"
    REFUSED = "refused"
    TRANSIENT_FAILURE = "transient_failure"
    PERMANENT_FAILURE = "permanent_failure"


@dataclass(frozen=True)
class AgentResponse:
    schema: str
    role: AgentRole
    disposition: Disposition
    observations: tuple[str, ...]
    actions: tuple[ProposedAction, ...]
    artifacts: tuple[ArtifactReference, ...]
    assumptions: tuple[str, ...]
    confidence: int
    usage: Usage
    validation_errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        check(self.schema == AGENT_RESPONSE_SCHEMA, "unsupported agent response schema")
        check(0 <= self.confidence <= 100, "invalid confidence")
        check(
            sum(len(value) for value in self.observations + self.assumptions) <= 64_000,
            "agent response too large",
        )
        object.__setattr__(self, "actions", tuple(self.actions))


def validate_response(request: AgentRequest, response: AgentResponse) -> None:
    check(response.role == request.role, "agent role escalation")
    check(
        all(action.action in request.allowed_actions for action in response.actions),
        "prohibited agent action",
    )
    check(
        all(action.action != ActionType.SKIP_VALIDATION for action in response.actions),
        "validation bypass prohibited",
    )


class EventKind(StrEnum):
    RUN_CREATED = "run_created"
    STATE_TRANSITION = "state_transition"
    AGENT_REQUESTED = "agent_requested"
    AGENT_ACCEPTED = "agent_accepted"
    AGENT_REJECTED = "agent_rejected"
    CANDIDATE_REGISTERED = "candidate_registered"
    CANDIDATE_REJECTED = "candidate_rejected"
    CANDIDATE_VALIDATED = "candidate_validated"
    RANKING_COMPLETED = "ranking_completed"
    BUDGET_CONSUMED = "budget_consumed"
    CHECKPOINT_CREATED = "checkpoint_created"
    HUMAN_DECISION = "human_decision"


@dataclass(frozen=True)
class RunEvent:
    sequence: int
    kind: EventKind
    run_id: str
    previous_fingerprint: str
    payload: tuple[tuple[str, str], ...]
    event_fingerprint: str = ""

    def __post_init__(self) -> None:
        check(self.sequence >= 0, "invalid event sequence")
        valid_id(self.run_id)
        digest(self.previous_fingerprint)
        object.__setattr__(self, "payload", tuple(sorted(self.payload)))
        check(len({key for key, _ in self.payload}) == len(self.payload), "duplicate event field")
        expected = fingerprint({k: v for k, v in asdict(self).items() if k != "event_fingerprint"})
        if self.event_fingerprint:
            check(self.event_fingerprint == expected, "event fingerprint mismatch")
        else:
            object.__setattr__(self, "event_fingerprint", expected)


def append_event(
    events: tuple[RunEvent, ...],
    kind: EventKind,
    run_id: str,
    payload: tuple[tuple[str, str], ...] = (),
) -> tuple[RunEvent, ...]:
    previous = events[-1].event_fingerprint if events else ZERO_FINGERPRINT
    return (*events, RunEvent(len(events), kind, run_id, previous, payload))


def validate_event_chain(events: tuple[RunEvent, ...], run_id: str) -> str:
    previous = ZERO_FINGERPRINT
    for sequence, event in enumerate(events):
        check(event.sequence == sequence, "invalid event ordering")
        check(event.run_id == run_id, "cross-run event")
        check(event.previous_fingerprint == previous, "broken event chain")
        check(
            replace(event, event_fingerprint="").event_fingerprint == event.event_fingerprint,
            "altered event",
        )
        previous = event.event_fingerprint
    return previous


@dataclass(frozen=True, order=True)
class CandidateEvidence:
    candidate_id: str
    patch: ArtifactReference
    state: CandidateState
    architecture_accepted: bool
    functional_accepted: bool
    infrastructure_healthy: bool
    regressions: int
    fixed_targets: int
    architecture_introduced: int
    persistent_failures: int
    patch_bytes: int
    changed_files: int
    rejection_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        valid_id(self.candidate_id)
        check(
            all(
                value >= 0
                for value in (
                    self.regressions,
                    self.fixed_targets,
                    self.architecture_introduced,
                    self.persistent_failures,
                    self.patch_bytes,
                    self.changed_files,
                )
            ),
            "invalid candidate metric",
        )
        object.__setattr__(self, "rejection_reasons", tuple(sorted(set(self.rejection_reasons))))
        if self.state in {CandidateState.VALIDATED, CandidateState.RANKED, CandidateState.SELECTED}:
            check(
                self.architecture_accepted
                and self.functional_accepted
                and self.infrastructure_healthy,
                "validated candidate lacks mandatory evidence",
            )

    def transition(self, target: CandidateState) -> "CandidateEvidence":
        check(
            target in CANDIDATE_TRANSITIONS.get(self.state, set()), "illegal candidate transition"
        )
        return replace(self, state=target)


def candidate_rank_key(value: CandidateEvidence) -> tuple[object, ...]:
    accepted = (
        value.architecture_accepted and value.functional_accepted and value.infrastructure_healthy
    )
    return (
        not accepted,
        value.regressions,
        -value.fixed_targets,
        value.architecture_introduced,
        value.persistent_failures,
        value.patch_bytes,
        value.changed_files,
        value.patch.sha256,
    )


def rank_candidates(values: tuple[CandidateEvidence, ...]) -> tuple[CandidateEvidence, ...]:
    check(len({value.patch.sha256 for value in values}) == len(values), "duplicate patch candidate")
    return tuple(sorted(values, key=candidate_rank_key))


@dataclass(frozen=True)
class RepairCheckpoint:
    schema: str
    run_id: str
    spec_fingerprint: str
    state: RunState
    last_sequence: int
    event_chain_fingerprint: str
    remaining_budget: Budget
    candidates: tuple[CandidateEvidence, ...]
    selected_candidate_id: str | None
    pending_human_decision: bool
    checkpoint_fingerprint: str = ""

    def __post_init__(self) -> None:
        check(self.schema == CHECKPOINT_SCHEMA, "unsupported checkpoint schema")
        valid_id(self.run_id)
        digest(self.spec_fingerprint)
        digest(self.event_chain_fingerprint)
        object.__setattr__(self, "candidates", tuple(self.candidates))
        check(
            len({item.candidate_id for item in self.candidates}) == len(self.candidates),
            "duplicate checkpoint candidate",
        )
        expected = fingerprint(
            {k: v for k, v in asdict(self).items() if k != "checkpoint_fingerprint"}
        )
        if self.checkpoint_fingerprint:
            check(self.checkpoint_fingerprint == expected, "checkpoint fingerprint mismatch")
        else:
            object.__setattr__(self, "checkpoint_fingerprint", expected)


class HumanDecisionKind(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    REVISE = "revise"
    CANCEL = "cancel"


@dataclass(frozen=True)
class HumanDecision:
    schema: str
    run_id: str
    candidate_id: str
    checkpoint_fingerprint: str
    decision: HumanDecisionKind

    def __post_init__(self) -> None:
        check(self.schema == HUMAN_DECISION_SCHEMA, "unsupported human decision schema")
        valid_id(self.run_id)
        valid_id(self.candidate_id)
        digest(self.checkpoint_fingerprint)


def verify_checkpoint(
    checkpoint: RepairCheckpoint, spec: RepairRunSpec, events: tuple[RunEvent, ...]
) -> None:
    check(checkpoint.run_id == spec.run_id, "checkpoint run mismatch")
    check(checkpoint.spec_fingerprint == spec.spec_fingerprint, "stale checkpoint specification")
    chain = validate_event_chain(events, spec.run_id)
    check(
        checkpoint.last_sequence == len(events) - 1 and checkpoint.event_chain_fingerprint == chain,
        "stale checkpoint event chain",
    )
