"""Strict source-free import and validation for the Phase 13 incident checkpoint."""

import hashlib
import json
import stat
import zipfile
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Any

from archguard.domain.canonical import canonical_json
from archguard.domain.orchestration import fingerprint
from archguard.domain.phase13 import (
    MODEL,
    POPULATION_FINGERPRINT,
    PROVIDER_FINGERPRINT,
    RESULT_SCHEMA,
    ResumeStopClassification,
    ResumeStopReason,
    classify_resume_stop,
    experiment_id,
)

ARCHIVE_SHA256 = "2004229eba0a901150335d2133dc345e551badd76cb763618fccf0afea41e31d"
PROTOCOL_FINGERPRINT = "eae1920ce71c025d2d94096798daf8b14df098249743631efe9a0aa7a541fbe8"
INCIDENT_FINGERPRINT = "71f60e3969313f139c493cad31ee20640fd6c2870d70411debdd5ab1956994e1"
CHECKPOINT_SCHEMA = "archguard.phase-13-checkpoint/v1"
MAX_ARCHIVE_BYTES = 32_768
MAX_MEMBER_BYTES = 4_096
MEMBERS = frozenset(
    {
        "home/runner/work/_temp/provider-preflight.json",
        "home/runner/work/_temp/checkpoint.json",
        "tmp/archguard-phase13-cost-state.json",
        "tmp/archguard-phase13-evidence/cleanup.json",
        "tmp/archguard-phase13-evidence/cost-state.json",
        "tmp/archguard-phase13-evidence/execution-1.json",
        "tmp/archguard-phase13-evidence/execution-2.json",
        "tmp/archguard-phase13-evidence/execution-3.json",
        "tmp/archguard-phase13-evidence/execution-4.json",
        "tmp/archguard-phase13-evidence/manifest.json",
        "tmp/archguard-phase13-evidence/pre-provider-failure.json",
    }
)


def import_checkpoint(archive: Path, incident_fingerprint: str) -> dict[str, Any]:
    raw = archive.read_bytes()
    if len(raw) > MAX_ARCHIVE_BYTES or hashlib.sha256(raw).hexdigest() != ARCHIVE_SHA256:
        raise ValueError("checkpoint archive identity mismatch")
    values: dict[str, dict[str, Any]] = {}
    with zipfile.ZipFile(archive) as bundle:
        infos = bundle.infolist()
        names = [item.filename for item in infos]
        if len(names) != len(set(names)) or set(names) != MEMBERS:
            raise ValueError("checkpoint archive members mismatch")
        for info in infos:
            path = PurePosixPath(info.filename)
            mode = info.external_attr >> 16
            if path.is_absolute() or ".." in path.parts or stat.S_ISLNK(mode):
                raise ValueError("unsafe checkpoint archive member")
            if info.file_size > MAX_MEMBER_BYTES or info.compress_size > MAX_MEMBER_BYTES:
                raise ValueError("checkpoint archive member too large")
            payload = bundle.read(info)
            value = json.loads(payload)
            if not isinstance(value, dict):
                raise ValueError("invalid checkpoint JSON object")
            values[info.filename] = value
    _validate_archive_values(values)
    executions = [
        values[f"tmp/archguard-phase13-evidence/execution-{ordinal}.json"]
        for ordinal in range(1, 5)
    ]
    call_ids = values["tmp/archguard-phase13-evidence/cost-state.json"]["call_ids"]
    checkpoint: dict[str, Any] = {
        "schema": CHECKPOINT_SCHEMA,
        "archive_sha256": ARCHIVE_SHA256,
        "incident_fingerprint": incident_fingerprint,
        "population_fingerprint": POPULATION_FINGERPRINT,
        "protocol_fingerprint": PROTOCOL_FINGERPRINT,
        "provider_configuration_fingerprint": PROVIDER_FINGERPRINT,
        "experiment_id": experiment_id(PROTOCOL_FINGERPRINT),
        "completed_ordinals": [1, 2, 3, 4],
        "next_ordinal": 5,
        "remaining_ordinals": [5, 6],
        "carried_observed_usd": "0.1296325",
        "carried_provider_calls": 4,
        "attempted_retries": 0,
        "historical_stop_reason": ResumeStopReason.PRE_PROVIDER_FAILURE.value,
        "historical_stop_classification": (
            ResumeStopClassification.CORRECTED_CHECKOUT_ACQUISITION_BUG.value
        ),
        "historical_pre_provider_failure": values[
            "tmp/archguard-phase13-evidence/pre-provider-failure.json"
        ],
        "active_stop_reason": None,
        "resume_allowed": True,
        "call_ledger": [
            {
                "call_id": call_id,
                "ordinal": ordinal,
                "completed": True,
                "usage_recorded": True,
            }
            for ordinal, call_id in enumerate(call_ids, start=1)
        ],
        "completed_executions": executions,
    }
    checkpoint["checkpoint_fingerprint"] = fingerprint(checkpoint)
    return checkpoint


def load_checkpoint(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict) or raw != canonical_json(value):
        raise ValueError("non-canonical Phase 13 checkpoint")
    recorded = value.get("checkpoint_fingerprint")
    actual = fingerprint(
        {key: item for key, item in value.items() if key != "checkpoint_fingerprint"}
    )
    if recorded != actual:
        raise ValueError("checkpoint fingerprint mismatch")
    try:
        policy = classify_resume_stop(
            ResumeStopReason(value["historical_stop_reason"]),
            ResumeStopClassification(value["historical_stop_classification"]),
        )
    except (KeyError, ValueError) as error:
        raise ValueError("invalid checkpoint resume policy") from error
    if (
        value.get("schema") != CHECKPOINT_SCHEMA
        or value.get("archive_sha256") != ARCHIVE_SHA256
        or value.get("incident_fingerprint") != INCIDENT_FINGERPRINT
        or value.get("population_fingerprint") != POPULATION_FINGERPRINT
        or value.get("protocol_fingerprint") != PROTOCOL_FINGERPRINT
        or value.get("provider_configuration_fingerprint") != PROVIDER_FINGERPRINT
        or value.get("experiment_id") != experiment_id(PROTOCOL_FINGERPRINT)
        or value.get("completed_ordinals") != [1, 2, 3, 4]
        or value.get("next_ordinal") != 5
        or value.get("remaining_ordinals") != [5, 6]
        or value.get("carried_observed_usd") != "0.1296325"
        or value.get("carried_provider_calls") != 4
        or value.get("attempted_retries") != 0
        or value.get("active_stop_reason") is not None
        or value.get("resume_allowed") is not policy.resume_allowed
        or not policy.resume_allowed
    ):
        raise ValueError("checkpoint invariant mismatch")
    executions = value.get("completed_executions")
    ledger = value.get("call_ledger")
    if not isinstance(executions, list) or len(executions) != 4:
        raise ValueError("invalid checkpoint executions")
    if not isinstance(ledger, list) or len(ledger) != 4:
        raise ValueError("invalid checkpoint call ledger")
    for ordinal, execution in enumerate(executions, start=1):
        _validate_execution(execution, ordinal)
    call_ids = [item.get("call_id") for item in ledger if isinstance(item, dict)]
    if (
        len(call_ids) != len(set(call_ids))
        or len(call_ids) != 4
        or any(not isinstance(call_id, str) or len(call_id) != 64 for call_id in call_ids)
    ):
        raise ValueError("duplicate or malformed checkpoint call identity")
    return value


def _validate_archive_values(values: dict[str, dict[str, Any]]) -> None:
    preflight = values["home/runner/work/_temp/provider-preflight.json"]
    initial = values["tmp/archguard-phase13-cost-state.json"]
    cleanup = values["tmp/archguard-phase13-evidence/cleanup.json"]
    cost = values["tmp/archguard-phase13-evidence/cost-state.json"]
    executions = [values[f"tmp/archguard-phase13-evidence/execution-{n}.json"] for n in range(1, 5)]
    manifest = values["tmp/archguard-phase13-evidence/manifest.json"]
    diagnostic = values["tmp/archguard-phase13-evidence/pre-provider-failure.json"]
    if (
        preflight.get("schema") != "archguard.provider-preflight/v1"
        or preflight.get("network_request") is not False
    ):
        raise ValueError("invalid imported preflight")
    if (
        initial.get("completed_primary_executions") != 0
        or initial.get("observed_provider_cost_usd") != "0"
    ):
        raise ValueError("invalid imported initial state")
    if cleanup != {"complete": True, "schema": "archguard.phase-13-cleanup/v1"}:
        raise ValueError("incomplete imported cleanup")
    for ordinal, execution in enumerate(executions, start=1):
        _validate_execution(execution, ordinal)
    execution_hashes = [hashlib.sha256(canonical_json(item)).hexdigest() for item in executions]
    if (
        cost.get("schema") != "archguard.phase-13-cost-state/v1"
        or cost.get("completed_primary") != 4
        or cost.get("provider_calls_started") != 4
        or cost.get("provider_calls_completed") != 4
        or cost.get("provider_calls_with_usage") != 4
        or cost.get("observed_usd") != "0.1296325"
        or manifest.get("schema") != "archguard.phase-13-manifest/v1"
        or manifest.get("completed_executions") != 4
        or manifest.get("provider_calls_completed") != 4
        or manifest.get("total_cost_usd") != "0.1296325"
        or manifest.get("result_fingerprints") != execution_hashes
        or diagnostic
        != {
            "condition": "baseline",
            "diagnostic_fingerprint": INCIDENT_FINGERPRINT,
            "exception_category": "validation_failure",
            "run_ordinal": 5,
            "stage": "checkout",
            "task_id": "black-4",
        }
    ):
        raise ValueError("imported incident evidence mismatch")


def _validate_execution(value: Any, ordinal: int) -> None:
    if not isinstance(value, dict):
        raise ValueError("invalid imported execution")
    required_hashes = (
        "request_fingerprint",
        "context_manifest_fingerprint",
        "response_fingerprint",
        "patch_fingerprint",
    )
    if (
        value.get("schema") != RESULT_SCHEMA
        or value.get("experiment_id") != experiment_id(PROTOCOL_FINGERPRINT)
        or value.get("population_fingerprint") != POPULATION_FINGERPRINT
        or value.get("protocol_fingerprint") != PROTOCOL_FINGERPRINT
        or value.get("provider_configuration_fingerprint") != PROVIDER_FINGERPRINT
        or value.get("model_snapshot") != MODEL
        or (
            value.get("run_ordinal"),
            value.get("task_id"),
            value.get("project"),
            value.get("condition"),
        )
        != {
            1: (1, "PySnooper-2", "PySnooper", "baseline"),
            2: (2, "PySnooper-2", "PySnooper", "archguard"),
            3: (3, "PySnooper-3", "PySnooper", "baseline"),
            4: (4, "PySnooper-3", "PySnooper", "archguard"),
        }[ordinal]
        or value.get("terminal_classification") != "invalid_patch"
        or value.get("patch_parsed") is not False
        or value.get("patch_applied") is not False
        or value.get("evaluator_executed") is not False
        or value.get("observed_usd")
        != {1: "0.025945", 2: "0.06102", 3: "0.0091625", 4: "0.033505"}[ordinal]
        or value.get("usage")
        != {
            1: {
                "cached_input_tokens": 0,
                "input_tokens": 5200,
                "output_tokens": 863,
                "reasoning_tokens": 0,
            },
            2: {
                "cached_input_tokens": 0,
                "input_tokens": 15108,
                "output_tokens": 1550,
                "reasoning_tokens": 0,
            },
            3: {
                "cached_input_tokens": 0,
                "input_tokens": 2621,
                "output_tokens": 174,
                "reasoning_tokens": 0,
            },
            4: {
                "cached_input_tokens": 0,
                "input_tokens": 12502,
                "output_tokens": 150,
                "reasoning_tokens": 0,
            },
        }[ordinal]
        or any(
            not isinstance(value.get(key), str) or len(value[key]) != 64 for key in required_hashes
        )
    ):
        raise ValueError("imported execution mismatch")
    usage = value["usage"]
    expected_cost = (
        Decimal(usage["input_tokens"]) * Decimal("2.50")
        + Decimal(usage["output_tokens"]) * Decimal("15.00")
    ) / Decimal("1000000")
    if expected_cost != Decimal(value["observed_usd"]):
        raise ValueError("imported execution cost mismatch")
