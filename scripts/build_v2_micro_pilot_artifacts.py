"""Build canonical, source-free V2.1A readiness artifacts without provider access."""

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def identified(value: dict[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result["fingerprint"] = hashlib.sha256(canonical(value)).hexdigest()
    return result


def write(relative: str, value: dict[str, Any]) -> None:
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(identified(value)))


def task_manifest(task: str) -> dict[str, Any]:
    common: dict[str, Any] = {
        "schema": "archguard.v2-task-manifest/v1",
        "project": "PySnooper",
        "repository": "https://github.com/cool-RR/PySnooper",
        "architecture_profile_fingerprint": (
            "950cd9889d5d4335e60b7429d2feddf2230db42654e5ec844edd813596b6d6d7"
        ),
        "patch_policy_fingerprint": (
            "ec892a22b76820bb17d98ebc5f315759d9a491ca9c6287c820bbf614bd21c779"
        ),
        "sandbox_plan": {
            "docker_socket": False,
            "network": "none",
            "no_new_privileges": True,
            "read_only_root": True,
            "user": "non-root",
        },
        "resource_ceilings": {
            "cpus": 2,
            "disk_bytes": 8589934592,
            "memory_bytes": 2147483648,
            "output_bytes": 1048576,
            "pids": 256,
            "timeout_seconds": 1200,
        },
        "platform_requirement": "Linux-x86_64",
        "gold_quarantine_policy": "READ_ONLY_FIXED_TEST_NO_AGENT_ACCESS",
        "source_free_evidence_policy": "NO_SOURCE_PROMPT_RAW_RESPONSE_GOLD_SECRET_OR_LOCAL_PATH",
        "cleanup_required": True,
        "external_execution_performed_in_v2_1a": False,
    }
    if task == "PySnooper-2":
        common.update(
            task_id=task,
            buggy_revision="e21a31162f4c54be693d8ca8260e42393b39abd3",
            fixed_revision="814abc34a098c1b98cb327105ac396f985d2413e",
            buggy_tree_identity="999fdc6713e170e36ba077eda47294c66d2167b1",
            fixed_tree_identity=None,
            tree_identity_status="HISTORICAL_FIXED_TREE_IDENTITY_NOT_RETAINED",
            license_evidence={
                "spdx": "MIT",
                "sha256": "5db83d6347f7e52946b736c71d0d59bb80c8a4485fcfa0a5140bdd839152be88",
                "status": "VERIFIED",
            },
            evaluator_adapter_fingerprint="15af404133824d1f026ebc33e4e4ac2a2e5cfc734e77862b7f5e90576f56f5fb",
            repository_graph_fingerprint="b1c318faba70d50225ceba74254edb18727013291de8607695334f8f0a98802c",
            qualification_evidence_fingerprint="a3a361aecb2c6c3eb3a1bcf570e148da1c98e49f1260f0f96fdf9f6e9f51ccf9",
            failure_signature="23d218f9cbe0d6ef4c78b18518b56d162edc43b3b234854218807d91e40aafc1",
            expected_buggy_failure="STABLE_EXPECTED_FAILURE",
            expected_fixed_success="PASSED",
            static_preflight_status="BLOCKED",
            blocker_codes=["FIXED_TREE_IDENTITY_RECHECK_REQUIRED"],
        )
    else:
        common.update(
            task_id=task,
            buggy_revision="6e3d797be3fa0a746fb5b1b7c7fea78eb926c208",
            fixed_revision="15555ed760000b049aff8fecc79d29339c1224c3",
            buggy_tree_identity="1afca46be552af2f9ace002d4b2ad13ca45bbfd3",
            fixed_tree_identity="b6bd4890f2f0ca2ae1bf933030cb071be6e29820",
            tree_identity_status="HISTORICALLY_VERIFIED",
            license_evidence={
                "spdx": "MIT",
                "sha256": "0c4250d2a9f0e39d024593ede44eb5044e5fbd1175a8962ec9659d8ace34de9e",
                "status": "VERIFIED",
            },
            evaluator_adapter_fingerprint="735cd3b2e75d89388b39c3815cee6fc1cb96ccb8938a4d86247ebfda0748f8ad",
            repository_graph_fingerprint=None,
            qualification_evidence_fingerprint="f975e236f0394bcf0138073919119c2df4f2f3d9961abdc781c18d6b2721f7c1",
            failure_signature="5fd6e966eb198a67f64527a9f99868c4b18481f1e76f236af6fac41585d4c628",
            expected_buggy_failure="STABLE_EXPECTED_FAILURE",
            expected_fixed_success="PASSED",
            static_preflight_status="STATIC_VALIDATED_EXTERNAL_EXECUTION_REQUIRED",
            blocker_codes=[],
        )
    return common


def main() -> None:
    pricing = {
        "schema": "archguard.v2-provider-pricing/v1",
        "provider": "openai",
        "api": "responses",
        "model_snapshot": "gpt-5.4-2026-03-05",
        "retrieval_date": "2026-11-04",
        "currency": "USD",
        "unit_tokens": 1000000,
        "standard_input": "2.50",
        "cached_input": "0.25",
        "output": "15.00",
        "long_context_note": (
            "Prompts above 272K input tokens use different pricing; this pilot caps input at 35K."
        ),
        "official_sources": [
            "https://developers.openai.com/api/docs/models/gpt-5.4",
            "https://developers.openai.com/api/docs/pricing",
        ],
    }
    call_plan = {
        "schema": "archguard.v2-micro-pilot-call-plan/v1",
        "status": "FROZEN_PROSPECTIVE_ENGINEERING_FEASIBILITY",
        "tasks": ["PySnooper-2", "PySnooper-3"],
        "conditions": ["BASELINE", "GRAPH_ONLY", "GRAPH_CONSTRAINTS", "FULL_ARCHGUARD"],
        "order": [
            f"{task}:{condition}"
            for task in ("PySnooper-2", "PySnooper-3")
            for condition in ("BASELINE", "GRAPH_ONLY", "GRAPH_CONSTRAINTS", "FULL_ARCHGUARD")
        ],
        "maximum_primary_calls": 8,
        "retries": 0,
        "maximum_input_tokens_per_call": 35000,
        "maximum_output_tokens_per_call": 2000,
        "reasoning_effort": "medium",
        "per_call_reservation_usd": "0.1175",
        "maximum_reserved_cost_usd": "0.9400",
        "absolute_ceiling_usd": "1.0000",
        "reserve_before_call": True,
        "usage_reconciliation_required": True,
        "cached_discount_used_for_admission": False,
        "automatic_continuation": False,
        "parallel_calls": False,
        "provider_tools": [],
        "response_schema": "archguard.repair-response/v2.1",
        "model_snapshot": "gpt-5.4-2026-03-05",
    }
    shared = {
        "model_snapshot": "gpt-5.4-2026-03-05",
        "response_schema": "archguard.repair-response/v2.1",
        "maximum_input_tokens": 35000,
        "maximum_output_tokens": 2000,
        "maximum_calls_per_pair": 1,
        "retries": 0,
        "patch_validator": "archguard.phase5-strict-unified-diff/v1",
        "sandbox": "docker-network-none-no-socket",
        "evaluator": "task-bound-frozen-adapter",
        "task_revisions": "manifest-bound",
        "resource_ceilings": "manifest-bound-identical",
        "failure_classifications": "v2-prospective-stable-taxonomy",
    }
    variants = {
        "BASELINE": [False, False, False, False],
        "GRAPH_ONLY": [True, False, False, False],
        "GRAPH_CONSTRAINTS": [True, True, False, False],
        "FULL_ARCHGUARD": [True, True, True, True],
    }
    fairness = {
        "schema": "archguard.v2-condition-fairness/v1",
        "conditions": {
            name: {
                **shared,
                "graph_retrieval": flags[0],
                "architecture_constraints": flags[1],
                "orchestration": flags[2],
                "execution_feedback": flags[3],
            }
            for name, flags in variants.items()
        },
        "status": "FAIR",
        "non_permitted_differences": [],
    }
    manifests = {task: identified(task_manifest(task)) for task in ("PySnooper-2", "PySnooper-3")}
    readiness = {
        "schema": "archguard.v2-micro-pilot-readiness/v1",
        "status": "V2_MICRO_PILOT_BLOCKED",
        "V2_MICRO_PILOT_READY": False,
        "prepared": True,
        "human_authorization_required": True,
        "provider_calls_executed": 0,
        "scientific_executions": 0,
        "blocker_codes": ["PYSNOOPER_2_FIXED_TREE_IDENTITY_RECHECK_REQUIRED"],
        "task_preflight": {
            "PySnooper-2": "BLOCKED",
            "PySnooper-3": "STATIC_VALIDATED_EXTERNAL_EXECUTION_REQUIRED",
        },
        "external_execution_performed": False,
        "pricing_matches_frozen_proposal": True,
        "fairness_status": "FAIR",
        "security_high_or_critical_findings": 0,
        "maximum_calls": 8,
        "maximum_reserved_cost_usd": "0.9400",
        "absolute_ceiling_usd": "1.0000",
        "manifest_fingerprints": {task: value["fingerprint"] for task, value in manifests.items()},
    }
    for task, value in manifests.items():
        path = ROOT / f"research/v2/manifests/{task.lower()}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical(value))
    write("research/v2/provider/openai-gpt-5.4-2026-03-05-pricing.json", pricing)
    write("research/v2/protocol/micro-pilot-call-plan.json", call_plan)
    write("research/v2/protocol/condition-fairness-matrix.json", fairness)
    write("research/v2/readiness/micro-pilot-readiness.json", readiness)


if __name__ == "__main__":
    main()
