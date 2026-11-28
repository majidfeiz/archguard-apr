"""Fail-closed loading of the frozen V2.2 execution protocol."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from archguard.domain.canonical import canonical_json
from archguard.domain.v2_execution import CALL_ORDER, CONDITIONS, TASKS
from archguard.domain.v2_micro_pilot import (
    HARD_CEILING,
    MAX_CALLS,
    MAX_INPUT_TOKENS,
    MAX_OUTPUT_TOKENS,
    MODEL_SNAPSHOT,
    PER_CALL_RESERVATION,
    RESPONSE_SCHEMA,
    TOTAL_RESERVATION,
    validate_condition_fairness,
)
from archguard.infrastructure.json_codec import unique_object

EXPECTED_PRICING = "a2278b5a07524e9c14299c1a01120e4b10b47b175f4bc13eefc2bc713d1d8c11"
EXPECTED_MANIFESTS = {
    "PySnooper-2": "d06c9c7e182e927e0955e1538133d9185c3918c2da19ff47f05e493d0295417f",
    "PySnooper-3": "58f39d94d5918abe6028198a622e105a00ca6dbc808230a804e278ec2a78cd23",
}
EXPECTED_READINESS = "24e0eae7122f60ff20aa823b47b1d6263bdadbde66a6995616bc7767ffe363ed"
PRIOR_PROTOCOL = "7d714e14bee0acba48c72377b0a0a3e73e8dd830bc92a1949f4139858ad0268d"
AMENDED_PROTOCOL = "5a110f57dc86e1b4e932bf81e5905a71da65253ab93ed2b68f323f16bd681e05"
CAPABILITY_FINGERPRINT = "77159d4236788c99bf0886a9108f018035bf4c55307e337fb36c1c3b595d5118"
CAPABILITY_EVIDENCE_SHA256 = "8a6f9292b6c9cba66cc990d31172d47eb4aa5e97318c1aaa23cfc1d1fe68d18f"


@dataclass(frozen=True)
class FrozenProtocol:
    root: Path
    fingerprint: str
    pricing_fingerprint: str
    readiness_fingerprint: str
    manifest_fingerprints: tuple[tuple[str, str], ...]
    fairness_fingerprint: str


def _load(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    value = json.loads(raw, object_pairs_hook=unique_object)
    if not isinstance(value, dict) or canonical_json(value) != raw:
        raise ValueError(f"noncanonical protocol input: {path.name}")
    unsigned = {key: item for key, item in value.items() if key != "fingerprint"}
    if value.get("fingerprint") != hashlib.sha256(canonical_json(unsigned)).hexdigest():
        raise ValueError(f"fingerprint mismatch: {path.name}")
    return cast(dict[str, object], value)


def load_frozen_protocol(root: Path) -> FrozenProtocol:
    root = root.resolve()
    plan = _load(root / "research/v2/protocol/micro-pilot-call-plan.json")
    amendment = _load(root / "research/v2/protocol/micro-pilot-amendment-v3.json")
    pricing = _load(root / "research/v2/provider/openai-gpt-5.4-2026-03-05-pricing.json")
    readiness = _load(root / "research/v2/readiness/micro-pilot-readiness.json")
    amended_readiness = _load(root / "research/v2/readiness/amended-micro-pilot-readiness.json")
    capability_provenance = _load(root / "research/v2/evidence/provider-capability-provenance.json")
    capability_raw = (root / "research/v2/evidence/provider-capability-probe.json").read_bytes()
    fairness = _load(root / "research/v2/protocol/condition-fairness-matrix.json")
    manifests = {task: _load(root / f"research/v2/manifests/{task.lower()}.json") for task in TASKS}
    exact = {
        "tasks": list(TASKS),
        "conditions": list(CONDITIONS),
        "order": [f"{task}:{condition}" for task, condition in CALL_ORDER],
        "model_snapshot": MODEL_SNAPSHOT,
        "maximum_primary_calls": MAX_CALLS,
        "retries": 0,
        "maximum_input_tokens_per_call": MAX_INPUT_TOKENS,
        "maximum_output_tokens_per_call": MAX_OUTPUT_TOKENS,
        "per_call_reservation_usd": str(PER_CALL_RESERVATION),
        "maximum_reserved_cost_usd": str(TOTAL_RESERVATION),
        "absolute_ceiling_usd": str(HARD_CEILING),
        "response_schema": RESPONSE_SCHEMA,
        "provider_tools": [],
        "parallel_calls": False,
        "automatic_continuation": False,
    }
    for key, expected in exact.items():
        if plan.get(key) != expected:
            raise ValueError(f"frozen protocol mismatch: {key}")
    if plan.get("fingerprint") != PRIOR_PROTOCOL:
        raise ValueError("prior protocol fingerprint mismatch")
    if pricing.get("fingerprint") != EXPECTED_PRICING:
        raise ValueError("pricing fingerprint mismatch")
    if readiness.get("fingerprint") != EXPECTED_READINESS:
        raise ValueError("readiness fingerprint mismatch")
    if readiness.get("manifest_fingerprints") != EXPECTED_MANIFESTS:
        raise ValueError("readiness manifest binding mismatch")
    for task, expected in EXPECTED_MANIFESTS.items():
        if manifests[task].get("fingerprint") != expected:
            raise ValueError(f"task manifest fingerprint mismatch: {task}")
    if not (
        readiness.get("V2_MICRO_PILOT_READY") is True
        and readiness.get("prepared") is True
        and readiness.get("blocker_codes") == []
        and readiness.get("provider_calls_executed") == 0
        and readiness.get("scientific_executions") == 0
    ):
        raise ValueError("readiness is not pristine and authorized")
    if hashlib.sha256(capability_raw).hexdigest() != CAPABILITY_EVIDENCE_SHA256:
        raise ValueError("capability evidence hash mismatch")
    capability = json.loads(capability_raw, object_pairs_hook=unique_object)
    if not isinstance(capability, dict) or canonical_json(capability) != capability_raw:
        raise ValueError("capability evidence is not canonical")
    if not (
        capability.get("status") == "SUPPORTED"
        and capability.get("diagnostic_fingerprint") == CAPABILITY_FINGERPRINT
        and capability.get("accepted_provider_calls") == 1
        and capability.get("scientific_executions") == 0
        and capability.get("patch_semantics_valid") is False
    ):
        raise ValueError("capability evidence is not the frozen supported observation")
    if not (
        capability_provenance.get("status") == "FROZEN_SUPPORTED"
        and capability_provenance.get("capability_fingerprint") == CAPABILITY_FINGERPRINT
        and capability_provenance.get("evidence_json_sha256") == CAPABILITY_EVIDENCE_SHA256
    ):
        raise ValueError("capability provenance mismatch")
    if not (
        amendment.get("fingerprint") == AMENDED_PROTOCOL
        and amendment.get("prior_protocol_fingerprint") == PRIOR_PROTOCOL
        and amendment.get("call_order") == [f"{task}:{condition}" for task, condition in CALL_ORDER]
        and amendment.get("task_manifest_fingerprints") == EXPECTED_MANIFESTS
        and amendment.get("capability_fingerprint") == CAPABILITY_FINGERPRINT
        and amendment.get("clean_checkpoint_required") is True
        and amendment.get("historical_incident_run_id") == 45979876101
        and amendment.get("historical_valid_scientific_executions") == 0
        and amendment.get("historical_incident_in_primary_result_set") is False
    ):
        raise ValueError("prospective protocol amendment mismatch")
    if not (
        amended_readiness.get("V2_AMENDED_MICRO_PILOT_READY") is True
        and amended_readiness.get("status") == "READY"
        and amended_readiness.get("capability_status") == "FROZEN_SUPPORTED"
        and amended_readiness.get("protocol_fingerprint") == AMENDED_PROTOCOL
        and amended_readiness.get("blocker_codes") == []
        and amended_readiness.get("human_authorization_required") is True
        and amended_readiness.get("provider_calls_executed") == 0
        and amended_readiness.get("scientific_executions") == 0
        and amended_readiness.get("scientific_checkpoint_state") == "EMPTY_REQUIRED"
    ):
        raise ValueError("amended readiness mismatch")
    conditions = fairness.get("conditions")
    if not isinstance(conditions, dict) or validate_condition_fairness(conditions):
        raise ValueError("condition fairness mismatch")
    return FrozenProtocol(
        root,
        str(amendment["fingerprint"]),
        str(pricing["fingerprint"]),
        str(amended_readiness["fingerprint"]),
        tuple((task, str(manifests[task]["fingerprint"])) for task in TASKS),
        str(fairness["fingerprint"]),
    )
