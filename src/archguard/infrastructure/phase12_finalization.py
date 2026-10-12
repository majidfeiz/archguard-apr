"""Strict validation for the canonical Phase 12 closure records."""

import hashlib
import json
from pathlib import Path
from typing import Any

from archguard.domain.canonical import canonical_json
from archguard.domain.orchestration import fingerprint

QUALIFICATION_TASKS = (
    "PySnooper-1",
    "PySnooper-2",
    "PySnooper-3",
    "black-1",
    "black-2",
    "black-3",
    "black-4",
    "cookiecutter-4",
)
FROZEN_TASKS = ("PySnooper-2", "PySnooper-3", "black-4")


def _load_canonical(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict) or raw != canonical_json(value):
        raise ValueError(f"non-canonical Phase 12 record: {path.name}")
    return value


def _validate_fingerprint(value: dict[str, Any]) -> None:
    recorded = value.get("fingerprint")
    actual = fingerprint({key: item for key, item in value.items() if key != "fingerprint"})
    if recorded != actual:
        raise ValueError("Phase 12 record fingerprint mismatch")


def validate_qualification_registry(path: Path) -> dict[str, Any]:
    value = _load_canonical(path)
    if value.get("schema") != "archguard.qualification-registry/v1":
        raise ValueError("unsupported qualification registry")
    _validate_fingerprint(value)
    records = value.get("records")
    if (
        not isinstance(records, list)
        or tuple(item.get("task_id") for item in records) != QUALIFICATION_TASKS
    ):
        raise ValueError("qualification population drift")
    qualified = [item for item in records if item.get("qualification_decision") == "QUALIFIED"]
    if tuple(item["task_id"] for item in qualified) != FROZEN_TASKS:
        raise ValueError("qualified-task substitution")
    if any(item.get("platform") != "Linux-x86_64" for item in records):
        raise ValueError("qualification platform mismatch")
    expected = {
        "attempted_tasks": 8,
        "excluded_or_not_qualified_tasks": 5,
        "project_count": 3,
        "qualified_tasks": 3,
        "stable_tasks": 3,
        "total_selected_tasks": 8,
    }
    if value.get("counts") != expected or value.get("qualification_attrition") != {
        "denominator": 8,
        "excluded": 5,
        "numerator": 5,
    }:
        raise ValueError("qualification counts inconsistent")
    return value


def validate_population(path: Path, registry: dict[str, Any]) -> dict[str, Any]:
    value = _load_canonical(path)
    if value.get("schema") != "archguard.exploratory-population-freeze/v1":
        raise ValueError("unsupported population freeze")
    _validate_fingerprint(value)
    tasks = value.get("tasks")
    if not isinstance(tasks, list) or tuple(item.get("task_id") for item in tasks) != FROZEN_TASKS:
        raise ValueError("frozen task substitution")
    source = {item["task_id"]: item for item in registry["records"]}
    for item in tasks:
        expected = source[item["task_id"]]
        for key in (
            "adapter_fingerprint",
            "buggy_revision",
            "evidence_fingerprint",
            "fixed_revision",
            "project",
        ):
            if item.get(key) != expected.get(key):
                raise ValueError(f"frozen task binding drift: {key}")
    if value.get("replacement_policy") != "PROHIBITED_AFTER_FREEZE_NEW_PROTOCOL_REQUIRED":
        raise ValueError("outcome-based replacement not prohibited")
    return value


def validate_protocol(path: Path, population: dict[str, Any]) -> dict[str, Any]:
    value = _load_canonical(path)
    if value.get("schema") != "archguard.exploratory-feasibility-protocol/v1":
        raise ValueError("unsupported frozen protocol")
    _validate_fingerprint(value)
    definition = value.get("definition")
    if not isinstance(definition, dict) or value.get("definition_fingerprint") != fingerprint(
        definition
    ):
        raise ValueError("protocol definition drift")
    if value.get("population_fingerprint") != population.get("fingerprint"):
        raise ValueError("protocol population binding mismatch")
    provider = definition.get("provider")
    if provider != {
        "approved_cost": None,
        "maximum_calls": 0,
        "model": None,
        "price": None,
        "status": "PROVIDER_NOT_CONFIGURED",
    }:
        raise ValueError("unapproved provider configuration")
    return value


def validate_decision(
    path: Path, history_path: Path, population: dict[str, Any], protocol: dict[str, Any]
) -> dict[str, Any]:
    value = _load_canonical(path)
    if value.get("schema") != "archguard.human-decision/v4" or value.get("decision") != "APPROVE":
        raise ValueError("protocol is not approved")
    _validate_fingerprint(value)
    if (
        value.get("previous_decision_sha256")
        != hashlib.sha256(history_path.read_bytes()).hexdigest()
    ):
        raise ValueError("decision history binding mismatch")
    binding = value.get("approval_binding", {})
    if binding.get("population_fingerprint") != population.get("fingerprint") or binding.get(
        "protocol_definition_fingerprint"
    ) != protocol.get("definition_fingerprint"):
        raise ValueError("approval binding mismatch")
    if protocol.get("decision_fingerprint") != value.get("fingerprint"):
        raise ValueError("protocol decision binding mismatch")
    return value


def validate_phase12_closure(root: Path) -> dict[str, str]:
    registry = validate_qualification_registry(root / "evidence/qualification-registry-v1.json")
    population = validate_population(root / "population/exploratory-feasibility-v1.json", registry)
    protocol = validate_protocol(root / "protocol/exploratory-feasibility-v1.json", population)
    decision = validate_decision(
        root / "reviews/protocol-decision.json",
        root / "reviews/protocol-decision-history-v1.json",
        population,
        protocol,
    )
    return {
        "decision_fingerprint": str(decision["fingerprint"]),
        "population_fingerprint": str(population["fingerprint"]),
        "protocol_fingerprint": str(protocol["fingerprint"]),
        "qualification_registry_fingerprint": str(registry["fingerprint"]),
    }
