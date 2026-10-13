"""Canonical loading and hash-linked validation of the amended Phase 13 protocol."""

import json
from pathlib import Path
from typing import Any

from archguard.domain.canonical import canonical_json
from archguard.domain.orchestration import fingerprint
from archguard.domain.phase13 import (
    FROZEN_EXECUTIONS,
    POPULATION_FINGERPRINT,
    PROVIDER_FINGERPRINT,
)

HISTORICAL_PROTOCOL_FINGERPRINT = "93494690f402d17e511d9cad1fdc92907d408ae3a923139d30537894f9ab8ce7"


def load_phase13_protocol(path: Path) -> dict[str, Any]:
    value = _canonical(path)
    if value.get("schema") != "archguard.exploratory-feasibility-protocol/v2":
        raise ValueError("unsupported Phase 13 protocol")
    recorded = value.get("fingerprint")
    actual = fingerprint({key: item for key, item in value.items() if key != "fingerprint"})
    expected_order = [
        {
            "condition": item.condition.value,
            "ordinal": item.ordinal,
            "project": item.project,
            "task_id": item.task_id,
        }
        for item in FROZEN_EXECUTIONS
    ]
    if (
        recorded != actual
        or value.get("amends_protocol_fingerprint") != HISTORICAL_PROTOCOL_FINGERPRINT
    ):
        raise ValueError("Phase 13 protocol fingerprint drift")
    if value.get("population_fingerprint") != POPULATION_FINGERPRINT:
        raise ValueError("Phase 13 population drift")
    if value.get("execution_order") != expected_order:
        raise ValueError("Phase 13 execution order drift")
    if value.get("primary_executions") != 6 or value.get("repetitions_per_task_condition") != 1:
        raise ValueError("Phase 13 run count drift")
    provider = value.get("provider")
    if not isinstance(provider, dict) or provider != {
        "configuration_fingerprint": PROVIDER_FINGERPRINT,
        "fallback": False,
        "maximum_calls": 12,
        "model": "gpt-5.4-2026-03-05",
        "name": "openai",
        "status": "CONFIGURED",
    }:
        raise ValueError("Phase 13 provider drift")
    return value


def validate_amendment(path: Path, protocol: dict[str, Any]) -> dict[str, Any]:
    value = _canonical(path)
    recorded = value.get("amendment_fingerprint")
    actual = fingerprint(
        {key: item for key, item in value.items() if key != "amendment_fingerprint"}
    )
    if recorded != actual:
        raise ValueError("protocol amendment fingerprint drift")
    if (
        value.get("previous_protocol_fingerprint") != HISTORICAL_PROTOCOL_FINGERPRINT
        or value.get("new_protocol_fingerprint") != protocol["fingerprint"]
        or value.get("provider_configuration_fingerprint") != PROVIDER_FINGERPRINT
        or value.get("provider_calls_at_decision") != 0
        or value.get("observed_scientific_outcomes") != 0
        or value.get("observed_provider_cost_usd") != "0"
        or value.get("prospective") is not True
    ):
        raise ValueError("invalid prospective protocol amendment")
    return value


def _canonical(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict) or raw != canonical_json(value):
        raise ValueError("non-canonical Phase 13 artifact")
    return value
