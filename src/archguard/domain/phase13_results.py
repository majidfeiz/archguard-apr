"""Deterministic, descriptive-only aggregation for Phase 13 closure."""

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from archguard.domain.orchestration import fingerprint


def aggregate_phase13_results(executions: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate four immutable outcomes without inferring missing scientific results."""
    if [item.get("run_ordinal") for item in executions] != [1, 2, 3, 4]:
        raise ValueError("Phase 13 completed execution prefix mismatch")
    if any(item.get("terminal_classification") != "invalid_patch" for item in executions):
        raise ValueError("Phase 13 terminal classification mismatch")
    if any(item.get("repair_success") is not False for item in executions):
        raise ValueError("Phase 13 repair outcome mismatch")

    conditions: dict[str, dict[str, Any]] = {}
    for condition in ("baseline", "archguard"):
        selected = [item for item in executions if item.get("condition") == condition]
        if len(selected) != 2:
            raise ValueError("Phase 13 paired condition mismatch")
        input_tokens = sum(int(item["usage"]["input_tokens"]) for item in selected)
        output_tokens = sum(int(item["usage"]["output_tokens"]) for item in selected)
        conditions[condition] = {
            "executions": 2,
            "repair_successes": 0,
            "invalid_patches": 2,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "observed_usd": str(sum(Decimal(item["observed_usd"]) for item in selected)),
        }

    result: dict[str, Any] = {
        "schema": "archguard.phase-13-final-results/v1",
        "phase_13_complete_with_attrition": True,
        "phase_13_execution_status": "COMPLETED_WITH_ATTRITION",
        "planned_executions": 6,
        "completed_executions": 4,
        "completed_ordinals": [1, 2, 3, 4],
        "infrastructure_attrition": 2,
        "attrition_rate": "0.3333333333333333",
        "valid_paired_tasks": 2,
        "represented_projects": ["PySnooper"],
        "conditions": conditions,
        "invalid_patches": 4,
        "repair_successes": 0,
        "discordant_successful_pairs": 0,
        "descriptive_conclusion": "no_observed_effectiveness_difference",
        "inferential_testing": "not_performed_underpowered_zero_discordant_pairs",
        "study_scope": "exploratory_feasibility",
        "input_tokens": sum(int(item["usage"]["input_tokens"]) for item in executions),
        "output_tokens": sum(int(item["usage"]["output_tokens"]) for item in executions),
        "cached_input_tokens": sum(
            int(item["usage"]["cached_input_tokens"]) for item in executions
        ),
        "reasoning_tokens": sum(int(item["usage"]["reasoning_tokens"]) for item in executions),
        "observed_usd": str(sum(Decimal(item["observed_usd"]) for item in executions)),
    }
    result["total_tokens"] = result["input_tokens"] + result["output_tokens"]
    result["result_fingerprint"] = fingerprint(result)
    return result
