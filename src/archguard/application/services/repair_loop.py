"""Deterministic repair-loop policy over provider-neutral evidence."""

from dataclasses import dataclass, replace

from archguard.domain.patch_validation import CandidatePatch
from archguard.domain.repair import (
    TERMINAL_LOOP_STATES,
    CandidateLineage,
    PatchCandidate,
    PrecheckCode,
    PrecheckResult,
    RepairLoopState,
    RepairTask,
    ValidationEvidence,
    forbidden_change,
    path_allowed,
    rank_validated,
)

LEGAL_LOOP_TRANSITIONS = {
    RepairLoopState.TASK_VALIDATED: {
        RepairLoopState.CONTEXT_PREPARED,
        RepairLoopState.FAILED,
        RepairLoopState.CANCELLED,
    },
    RepairLoopState.CONTEXT_PREPARED: {
        RepairLoopState.ROUND_STARTED,
        RepairLoopState.FAILED,
        RepairLoopState.CANCELLED,
    },
    RepairLoopState.ROUND_STARTED: {
        RepairLoopState.CANDIDATES_REQUESTED,
        RepairLoopState.BUDGET_EXHAUSTED,
        RepairLoopState.CANCELLED,
    },
    RepairLoopState.CANDIDATES_REQUESTED: {
        RepairLoopState.CANDIDATE_RECEIVED,
        RepairLoopState.NO_ACCEPTABLE_CANDIDATE,
        RepairLoopState.FAILED,
        RepairLoopState.CANCELLED,
    },
    RepairLoopState.CANDIDATE_RECEIVED: {
        RepairLoopState.CANDIDATE_PRECHECKED,
        RepairLoopState.ROUND_COMPLETED,
        RepairLoopState.CANCELLED,
    },
    RepairLoopState.CANDIDATE_PRECHECKED: {
        RepairLoopState.CANDIDATE_VALIDATING,
        RepairLoopState.FEEDBACK_PREPARED,
        RepairLoopState.ROUND_COMPLETED,
        RepairLoopState.CANCELLED,
    },
    RepairLoopState.CANDIDATE_VALIDATING: {
        RepairLoopState.FEEDBACK_PREPARED,
        RepairLoopState.CANDIDATE_SELECTED,
        RepairLoopState.ROUND_COMPLETED,
        RepairLoopState.FAILED,
        RepairLoopState.CANCELLED,
    },
    RepairLoopState.FEEDBACK_PREPARED: {
        RepairLoopState.REFINEMENT_REQUESTED,
        RepairLoopState.ROUND_COMPLETED,
        RepairLoopState.NO_ACCEPTABLE_CANDIDATE,
        RepairLoopState.CANCELLED,
    },
    RepairLoopState.REFINEMENT_REQUESTED: {
        RepairLoopState.ROUND_COMPLETED,
        RepairLoopState.BUDGET_EXHAUSTED,
        RepairLoopState.CANCELLED,
    },
    RepairLoopState.ROUND_COMPLETED: {
        RepairLoopState.ROUND_STARTED,
        RepairLoopState.CONVERGED,
        RepairLoopState.CANDIDATE_SELECTED,
        RepairLoopState.NO_ACCEPTABLE_CANDIDATE,
        RepairLoopState.BUDGET_EXHAUSTED,
        RepairLoopState.CANCELLED,
    },
    RepairLoopState.CONVERGED: {
        RepairLoopState.CANDIDATE_SELECTED,
        RepairLoopState.NO_ACCEPTABLE_CANDIDATE,
    },
    RepairLoopState.CANDIDATE_SELECTED: {
        RepairLoopState.AWAITING_HUMAN_APPROVAL,
        RepairLoopState.COMPLETED,
    },
    RepairLoopState.AWAITING_HUMAN_APPROVAL: {
        RepairLoopState.COMPLETED,
        RepairLoopState.REFINEMENT_REQUESTED,
        RepairLoopState.CANCELLED,
    },
}


@dataclass(frozen=True)
class RepairLoopEvent:
    sequence: int
    previous_fingerprint: str
    state: RepairLoopState
    reason: str
    event_fingerprint: str = ""

    def __post_init__(self) -> None:
        from archguard.domain.orchestration import fingerprint

        expected = fingerprint(
            {
                "sequence": self.sequence,
                "previous_fingerprint": self.previous_fingerprint,
                "state": self.state,
                "reason": self.reason,
            }
        )
        if self.event_fingerprint:
            if self.event_fingerprint != expected:
                raise ValueError("repair event fingerprint mismatch")
        else:
            object.__setattr__(self, "event_fingerprint", expected)


def transition(
    events: tuple[RepairLoopEvent, ...], target: RepairLoopState, reason: str
) -> tuple[RepairLoopEvent, ...]:
    if not events:
        if target != RepairLoopState.TASK_VALIDATED:
            raise ValueError("repair loop must begin with task validation")
        previous = "0" * 64
    else:
        current = events[-1].state
        if current in TERMINAL_LOOP_STATES:
            raise ValueError("terminal repair-loop state")
        if target not in LEGAL_LOOP_TRANSITIONS.get(current, set()):
            raise ValueError("illegal repair-loop transition")
        previous = events[-1].event_fingerprint
    return (*events, RepairLoopEvent(len(events), previous, target, reason))


def precheck(
    task: RepairTask,
    raw: bytes,
    parsed: CandidatePatch,
    candidate: PatchCandidate,
    lineage: CandidateLineage,
) -> PrecheckResult:
    reasons: set[PrecheckCode] = set()
    if not parsed.acceptable:
        reasons.add(PrecheckCode.MALFORMED)
    if len(raw) > task.patch_policy.maximum_patch_bytes:
        reasons.add(PrecheckCode.TOO_LARGE)
    if len(parsed.changed_paths) > task.patch_policy.maximum_changed_files:
        reasons.add(PrecheckCode.TOO_MANY_FILES)
    if (
        candidate.added_lines > task.patch_policy.maximum_added_lines
        or candidate.deleted_lines > task.patch_policy.maximum_deleted_lines
    ):
        reasons.add(PrecheckCode.TOO_MANY_LINES)
    for path in parsed.changed_paths:
        if not path_allowed(path, task.patch_policy):
            reasons.add(
                PrecheckCode.PROTECTED_PATH
                if any(
                    path == item or path.startswith(item.rstrip("/") + "/")
                    for item in task.patch_policy.protected_paths
                )
                else PrecheckCode.OUTSIDE_SCOPE
            )
    if forbidden_change(raw):
        reasons.add(PrecheckCode.FORBIDDEN_CHANGE)
    if any(
        item.normalized_patch_fingerprint == candidate.normalized_patch_fingerprint
        for item in lineage.candidates
    ):
        reasons.add(PrecheckCode.DUPLICATE)
    if candidate.parent_candidate_id and candidate.parent_candidate_id not in {
        item.candidate_id for item in lineage.candidates
    }:
        reasons.add(PrecheckCode.INVALID_LINEAGE)
    return PrecheckResult(not reasons, tuple(reasons))


def add_candidate(lineage: CandidateLineage, candidate: PatchCandidate) -> CandidateLineage:
    duplicates = lineage.duplicates
    match = next(
        (
            item
            for item in lineage.candidates
            if item.normalized_patch_fingerprint == candidate.normalized_patch_fingerprint
        ),
        None,
    )
    if match:
        duplicates = tuple(sorted((*duplicates, (candidate.candidate_id, match.candidate_id))))
    return replace(
        lineage,
        candidates=tuple(
            sorted((*lineage.candidates, candidate), key=lambda item: item.candidate_id)
        ),
        duplicates=duplicates,
        lineage_fingerprint="",
    )


def select(
    task: RepairTask, validated: tuple[tuple[PatchCandidate, ValidationEvidence], ...]
) -> str | None:
    ranked = rank_validated(validated, task.acceptance)
    return ranked[0] if ranked else None


def replay(events: tuple[RepairLoopEvent, ...]) -> RepairLoopState:
    replayed: tuple[RepairLoopEvent, ...] = ()
    for event in events:
        replayed = transition(replayed, event.state, event.reason)
        if replayed[-1].event_fingerprint != event.event_fingerprint:
            raise ValueError("altered repair-loop event")
    if not replayed:
        raise ValueError("empty repair-loop event log")
    return replayed[-1].state
