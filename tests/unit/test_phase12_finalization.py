import json
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from archguard.domain.canonical import canonical_json
from archguard.domain.orchestration import fingerprint
from archguard.domain.readiness import readiness_report
from archguard.infrastructure.phase12_finalization import (
    validate_decision,
    validate_phase12_closure,
    validate_population,
    validate_protocol,
    validate_qualification_registry,
)


def _write_fingerprinted(path: Path, value: dict[str, object]) -> None:
    value["fingerprint"] = fingerprint(
        {key: item for key, item in value.items() if key != "fingerprint"}
    )
    path.write_bytes(canonical_json(value))


def test_phase12_closure_is_fingerprint_bound(repository_root: Path) -> None:
    result = validate_phase12_closure(repository_root / "research")
    assert result == {
        "decision_fingerprint": "2ff4adc5be719608860845d68be15c07205bf563423099a30c617e3d29170d7d",
        "population_fingerprint": (
            "421f3129ef6bee5883c41d05f087d6faff5b2a3de3b2ea543b4d27ade1488886"
        ),
        "protocol_fingerprint": "93494690f402d17e511d9cad1fdc92907d408ae3a923139d30537894f9ab8ce7",
        "qualification_registry_fingerprint": (
            "4b47b4c4b3042a572ff5e91969defbc25c3decd22b7a3fec0b0aae873586a1b3"
        ),
    }


def test_population_substitution_fails_closed(repository_root: Path, tmp_path: Path) -> None:
    source = repository_root / "research/population/exploratory-feasibility-v1.json"
    value = json.loads(source.read_text())
    value["tasks"][2]["task_id"] = "black-3"
    path = tmp_path / "population.json"
    path.write_bytes(canonical_json(value))
    registry = validate_qualification_registry(
        repository_root / "research/evidence/qualification-registry-v1.json"
    )
    with pytest.raises(ValueError, match="fingerprint|substitution"):
        validate_population(path, registry)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.update(schema="wrong"), "unsupported"),
        (lambda value: value["records"].reverse(), "population drift"),
        (
            lambda value: value["records"][0].update(qualification_decision="QUALIFIED"),
            "qualified-task substitution",
        ),
        (lambda value: value["records"][0].update(platform="Darwin-arm64"), "platform"),
        (lambda value: value["counts"].update(qualified_tasks=4), "counts"),
    ],
)
def test_qualification_registry_rejects_semantic_drift(
    repository_root: Path,
    tmp_path: Path,
    mutation: Callable[[dict[str, Any]], None],
    message: str,
) -> None:
    value = json.loads(
        (repository_root / "research/evidence/qualification-registry-v1.json").read_text()
    )
    mutation(value)
    path = tmp_path / "registry.json"
    _write_fingerprinted(path, value)
    with pytest.raises(ValueError, match=message):
        validate_qualification_registry(path)


def test_population_protocol_and_decision_reject_bound_drift(
    repository_root: Path, tmp_path: Path
) -> None:
    root = repository_root / "research"
    registry = validate_qualification_registry(root / "evidence/qualification-registry-v1.json")
    population = validate_population(root / "population/exploratory-feasibility-v1.json", registry)
    protocol = validate_protocol(root / "protocol/exploratory-feasibility-v1.json", population)

    changed_population = deepcopy(population)
    changed_population["tasks"][0]["adapter_fingerprint"] = "0" * 64
    population_path = tmp_path / "population.json"
    _write_fingerprinted(population_path, changed_population)
    with pytest.raises(ValueError, match="binding drift"):
        validate_population(population_path, registry)

    changed_population = deepcopy(population)
    changed_population["replacement_policy"] = "ALLOW"
    _write_fingerprinted(population_path, changed_population)
    with pytest.raises(ValueError, match="replacement"):
        validate_population(population_path, registry)

    changed_protocol = deepcopy(protocol)
    changed_protocol["definition"]["provider"]["model"] = "unapproved"
    changed_protocol["definition_fingerprint"] = fingerprint(changed_protocol["definition"])
    protocol_path = tmp_path / "protocol.json"
    _write_fingerprinted(protocol_path, changed_protocol)
    with pytest.raises(ValueError, match="provider"):
        validate_protocol(protocol_path, population)

    changed_protocol = deepcopy(protocol)
    changed_protocol["population_fingerprint"] = "0" * 64
    _write_fingerprinted(protocol_path, changed_protocol)
    with pytest.raises(ValueError, match="population binding"):
        validate_protocol(protocol_path, population)

    decision = json.loads((root / "reviews/protocol-decision.json").read_text())
    decision["previous_decision_sha256"] = "0" * 64
    decision_path = tmp_path / "decision.json"
    _write_fingerprinted(decision_path, decision)
    with pytest.raises(ValueError, match="history"):
        validate_decision(
            decision_path,
            root / "reviews/protocol-decision-history-v1.json",
            population,
            protocol,
        )

    decision = json.loads((root / "reviews/protocol-decision.json").read_text())
    decision["approval_binding"]["population_fingerprint"] = "0" * 64
    _write_fingerprinted(decision_path, decision)
    with pytest.raises(ValueError, match="approval binding"):
        validate_decision(
            decision_path,
            root / "reviews/protocol-decision-history-v1.json",
            population,
            protocol,
        )


def test_exploratory_readiness_separates_scientific_and_operational(
    repository_root: Path,
) -> None:
    facts = json.loads((repository_root / "research/readiness-facts.json").read_text())
    report = readiness_report(facts)
    assert report["phase_12_complete"] is True
    assert report["phase_13_scientifically_ready"] is True
    assert report["phase_13_operationally_ready"] is False
    assert report["blocker_codes"] == ["PROVIDER_NOT_CONFIGURED"]
