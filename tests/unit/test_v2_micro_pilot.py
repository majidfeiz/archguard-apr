import hashlib
import json
import re
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest
import yaml

from archguard.domain.canonical import canonical_json
from archguard.domain.v2_micro_pilot import (
    HARD_CEILING,
    MAX_CALLS,
    PER_CALL_RESERVATION,
    TOTAL_RESERVATION,
    CostState,
    SyntheticUsage,
    validate_condition_fairness,
)
from archguard.domain.v2_preflight import evaluate_preflight
from archguard.infrastructure.v2_preflight import load_v2_preflight_manifest

pytestmark = pytest.mark.unit


def load(root: Path, relative: str) -> dict[str, object]:
    return cast(dict[str, object], json.loads((root / relative).read_text()))


def assert_identity(value: dict[str, object]) -> None:
    fingerprint = value.pop("fingerprint")
    assert fingerprint == hashlib.sha256(canonical_json(value)).hexdigest()


def test_canonical_artifacts_have_stable_identities(repository_root: Path) -> None:
    paths = (
        "research/v2/manifests/pysnooper-2.json",
        "research/v2/manifests/pysnooper-3.json",
        "research/v2/provider/openai-gpt-5.4-2026-03-05-pricing.json",
        "research/v2/protocol/micro-pilot-call-plan.json",
        "research/v2/protocol/condition-fairness-matrix.json",
        "research/v2/evidence/pysnooper-2-fixed-tree-identity.json",
        "research/v2/readiness/pysnooper-2-identity-provenance.json",
        "research/v2/readiness/micro-pilot-readiness.json",
    )
    for relative in paths:
        path = repository_root / relative
        assert path.read_bytes().endswith(b"\n")
        value = json.loads(path.read_bytes())
        assert_identity(value)


def test_cost_guard_exact_boundaries_and_no_ninth_call() -> None:
    assert PER_CALL_RESERVATION == Decimal("0.1175")
    assert TOTAL_RESERVATION == Decimal("0.9400")
    assert HARD_CEILING == Decimal("1.0000")
    state = CostState()
    usage = SyntheticUsage(35_000, 2_000)
    assert usage.cost == PER_CALL_RESERVATION
    for _ in range(MAX_CALLS):
        state = state.reserve().reconcile(usage)
    assert state.completed_calls == 8 and state.observed_cost == TOTAL_RESERVATION
    with pytest.raises(ValueError, match="call ceiling"):
        state.reserve()


def test_cost_guard_fails_closed_on_ambiguity_and_usage_contradiction() -> None:
    with pytest.raises(ValueError, match="missing reservation"):
        CostState().reconcile(SyntheticUsage(1, 1))
    reserved = CostState().reserve()
    with pytest.raises(ValueError, match="missing provider usage"):
        reserved.reconcile(None)
    with pytest.raises(ValueError, match="in-flight"):
        reserved.reserve()
    with pytest.raises(ValueError, match="cost ceiling"):
        replace(CostState(), observed_cost=Decimal("0.90")).reserve()


def test_fairness_matrix_and_mutations(repository_root: Path) -> None:
    value = load(repository_root, "research/v2/protocol/condition-fairness-matrix.json")
    conditions = value["conditions"]
    assert isinstance(conditions, dict)
    assert validate_condition_fairness(conditions) == ()
    mutated = json.loads(json.dumps(conditions))
    mutated["GRAPH_ONLY"]["maximum_output_tokens"] = 2001
    assert validate_condition_fairness(mutated) == ("GRAPH_ONLY:maximum_output_tokens",)
    mutated = json.loads(json.dumps(conditions))
    mutated["BASELINE"]["extra_privilege"] = True
    with pytest.raises(ValueError, match="bad fields"):
        validate_condition_fairness(mutated)


def test_manifests_preserve_historical_bindings_and_integrate_identity(
    repository_root: Path,
) -> None:
    two = load(repository_root, "research/v2/manifests/pysnooper-2.json")
    three = load(repository_root, "research/v2/manifests/pysnooper-3.json")
    assert two["buggy_revision"] == "e21a31162f4c54be693d8ca8260e42393b39abd3"
    assert three["buggy_revision"] == "6e3d797be3fa0a746fb5b1b7c7fea78eb926c208"
    assert two["static_preflight_status"] == "READY"
    assert two["blocker_codes"] == []
    assert two["fixed_tree_identity"] == "d49244059559a6ae47051502fc88cf7fdb83beec"
    assert two["pre_import_manifest_fingerprint"] == (
        "400834ccce3146e41c6f30aedc334b017028b48bc14f7a08608ba86277efeba0"
    )
    assert two["fixed_tree_identity_evidence_fingerprint"] == (
        "a7e6c1d87d7366eb2aa6fb77ac0bd314b309471ce2466ffcaa3655e6cfd72fe4"
    )
    assert three["tree_identity_status"] == "HISTORICALLY_VERIFIED"
    assert two["external_execution_performed_in_v2_1a"] is False
    assert three["external_execution_performed_in_v2_1a"] is False
    two_result = evaluate_preflight(
        load_v2_preflight_manifest(repository_root / "research/v2/manifests/pysnooper-2.json")
    )
    three_result = evaluate_preflight(
        load_v2_preflight_manifest(repository_root / "research/v2/manifests/pysnooper-3.json")
    )
    assert two_result.status == "READY" and two_result.blocker_codes == ()
    assert three_result.status == "READY"


def test_task_manifest_rejects_contradictions_and_unknown_fields(
    repository_root: Path, tmp_path: Path
) -> None:
    source = load(repository_root, "research/v2/manifests/pysnooper-3.json")
    source["fixed_tree_identity"] = "0" * 40
    contradictory = tmp_path / "contradictory.json"
    contradictory.write_text(json.dumps(source))
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        load_v2_preflight_manifest(contradictory)

    source = load(repository_root, "research/v2/manifests/pysnooper-3.json")
    source["unexpected"] = True
    unknown = tmp_path / "unknown.json"
    unknown.write_text(json.dumps(source))
    with pytest.raises(ValueError, match="invalid V2 task manifest fields"):
        load_v2_preflight_manifest(unknown)

    source = load(repository_root, "research/v2/manifests/pysnooper-3.json")
    resources = cast(dict[str, object], source["resource_ceilings"])
    resources["pids"] = 0
    unsigned = {key: value for key, value in source.items() if key != "fingerprint"}
    source["fingerprint"] = hashlib.sha256(canonical_json(unsigned)).hexdigest()
    invalid_resources = tmp_path / "invalid-resources.json"
    invalid_resources.write_text(json.dumps(source))
    with pytest.raises(ValueError, match="invalid V2 task resource ceilings"):
        load_v2_preflight_manifest(invalid_resources)

    source = load(repository_root, "research/v2/manifests/pysnooper-2.json")
    source["fixed_tree_identity_evidence_sha256"] = "0" * 64
    unsigned = {key: value for key, value in source.items() if key != "fingerprint"}
    source["fingerprint"] = hashlib.sha256(canonical_json(unsigned)).hexdigest()
    invalid_provenance = tmp_path / "invalid-provenance.json"
    invalid_provenance.write_text(json.dumps(source))
    with pytest.raises(ValueError, match="invalid V2 identity provenance"):
        load_v2_preflight_manifest(invalid_provenance)


def test_pricing_call_plan_and_readiness_are_exact(repository_root: Path) -> None:
    pricing = load(repository_root, "research/v2/provider/openai-gpt-5.4-2026-03-05-pricing.json")
    plan = load(repository_root, "research/v2/protocol/micro-pilot-call-plan.json")
    readiness = load(repository_root, "research/v2/readiness/micro-pilot-readiness.json")
    assert (pricing["standard_input"], pricing["cached_input"], pricing["output"]) == (
        "2.50",
        "0.25",
        "15.00",
    )
    assert pricing["retrieval_date"] == "2026-11-04"
    order = plan["order"]
    assert isinstance(order, list) and len(order) == 8 and plan["retries"] == 0
    assert plan["provider_tools"] == [] and plan["parallel_calls"] is False
    assert readiness["V2_MICRO_PILOT_READY"] is True
    assert readiness["blocker_codes"] == []
    assert readiness["human_authorization_required"] is True
    assert readiness["workflow_triggered"] is False
    assert readiness["provider_calls_executed"] == readiness["scientific_executions"] == 0


def test_manual_workflow_is_safe_and_parseable(repository_root: Path) -> None:
    path = repository_root / ".github/workflows/v2-micro-pilot.yml"
    value = yaml.safe_load(path.read_text())
    assert set(value[True]) == {"workflow_dispatch"}
    source = path.read_text()
    assert "ubuntu-24.04" in source
    assert "cancel-in-progress: false" in source
    assert "OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}" in source
    assert "environment: v2-micro-pilot" in source
    assert "uv run pytest --no-cov tests/unit/test_v2_micro_pilot.py" in source
    assert "tests/unit/test_v2_preflight.py" in source
    assert "maximum_primary_calls == 8" in source
    assert ".retries == 0" in source
    assert '.maximum_reserved_cost_usd == "0.9400"' in source
    assert '.absolute_ceiling_usd == "1.0000"' in source
    assert "V2_MICRO_PILOT_READY == true" in source
    assert "if: always()" in source
    assert "workflow_dispatch" in source and "schedule:" not in source


def test_v2_artifacts_contain_no_secret_or_source_payload(repository_root: Path) -> None:
    payload = b"".join(
        path.read_bytes() for path in (repository_root / "research/v2").rglob("*.json")
    )
    assert b"OPENAI_API_KEY=" not in payload
    assert re.search(rb"(?<![A-Za-z])sk-[A-Za-z0-9_-]{20,}", payload) is None
    assert b"raw_provider_response" not in payload
    assert str(repository_root).encode() not in payload
