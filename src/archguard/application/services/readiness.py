"""Vendor-neutral Phase 12.8 review and readiness services."""

from dataclasses import asdict
from typing import Any

from archguard.domain.readiness import HumanDecisionRecord, readiness_report


def validate_human_decision(
    decision: HumanDecisionRecord, current_fingerprint: str
) -> dict[str, Any]:
    return {
        "decision": decision.decision,
        "fingerprint_matches": decision.reviewed_fingerprint == current_fingerprint,
        "approved": decision.approves(current_fingerprint),
        "record": asdict(decision),
    }


def aggregate_readiness(facts: dict[str, Any]) -> dict[str, Any]:
    return readiness_report(facts)
