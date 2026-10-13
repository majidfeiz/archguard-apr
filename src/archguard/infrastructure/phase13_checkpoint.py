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
    experiment_id,
)

ARCHIVE_SHA256 = "035c173e7505f8548996c2e18fcfdfaabf9b3ef3b29e221ba8b5f689c2df9952"
PROTOCOL_FINGERPRINT = "eae1920ce71c025d2d94096798daf8b14df098249743631efe9a0aa7a541fbe8"
INCIDENT_FINGERPRINT = "1962b2743ee2f36ba05a163d1331d8197f826708b937e0e9adadb093c3002617"
CHECKPOINT_SCHEMA = "archguard.phase-13-checkpoint/v1"
MAX_ARCHIVE_BYTES = 16_384
MAX_MEMBER_BYTES = 4_096
MEMBERS = frozenset(
    {
        "home/runner/work/_temp/provider-preflight.json",
        "tmp/archguard-phase13-cost-state.json",
        "tmp/archguard-phase13-evidence/cleanup.json",
        "tmp/archguard-phase13-evidence/cost-state.json",
        "tmp/archguard-phase13-evidence/execution-1.json",
        "tmp/archguard-phase13-evidence/manifest.json",
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
    execution = values["tmp/archguard-phase13-evidence/execution-1.json"]
    call_id = fingerprint(
        {
            "github_run_id": "38452767198",
            "ordinal": 1,
            "response_fingerprint": execution["response_fingerprint"],
        }
    )
    checkpoint: dict[str, Any] = {
        "schema": CHECKPOINT_SCHEMA,
        "archive_sha256": ARCHIVE_SHA256,
        "incident_fingerprint": incident_fingerprint,
        "population_fingerprint": POPULATION_FINGERPRINT,
        "protocol_fingerprint": PROTOCOL_FINGERPRINT,
        "provider_configuration_fingerprint": PROVIDER_FINGERPRINT,
        "experiment_id": experiment_id(PROTOCOL_FINGERPRINT),
        "completed_ordinals": [1],
        "next_ordinal": 2,
        "remaining_ordinals": [2, 3, 4, 5, 6],
        "carried_observed_usd": "0.025945",
        "carried_provider_calls": 1,
        "attempted_retries": 0,
        "call_ledger": [
            {
                "call_id": call_id,
                "ordinal": 1,
                "completed": True,
                "usage_recorded": True,
            }
        ],
        "completed_executions": [execution],
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
    if (
        value.get("schema") != CHECKPOINT_SCHEMA
        or value.get("archive_sha256") != ARCHIVE_SHA256
        or value.get("incident_fingerprint") != INCIDENT_FINGERPRINT
        or value.get("population_fingerprint") != POPULATION_FINGERPRINT
        or value.get("protocol_fingerprint") != PROTOCOL_FINGERPRINT
        or value.get("provider_configuration_fingerprint") != PROVIDER_FINGERPRINT
        or value.get("experiment_id") != experiment_id(PROTOCOL_FINGERPRINT)
        or value.get("completed_ordinals") != [1]
        or value.get("next_ordinal") != 2
        or value.get("remaining_ordinals") != [2, 3, 4, 5, 6]
        or value.get("carried_observed_usd") != "0.025945"
        or value.get("carried_provider_calls") != 1
        or value.get("attempted_retries") != 0
    ):
        raise ValueError("checkpoint invariant mismatch")
    executions = value.get("completed_executions")
    ledger = value.get("call_ledger")
    if not isinstance(executions, list) or len(executions) != 1:
        raise ValueError("invalid checkpoint executions")
    if not isinstance(ledger, list) or len(ledger) != 1:
        raise ValueError("invalid checkpoint call ledger")
    _validate_execution(executions[0])
    call_ids = [item.get("call_id") for item in ledger if isinstance(item, dict)]
    if (
        len(call_ids) != len(set(call_ids))
        or len(call_ids) != 1
        or any(not isinstance(call_id, str) or len(call_id) != 64 for call_id in call_ids)
    ):
        raise ValueError("duplicate or malformed checkpoint call identity")
    return value


def _validate_archive_values(values: dict[str, dict[str, Any]]) -> None:
    preflight = values["home/runner/work/_temp/provider-preflight.json"]
    initial = values["tmp/archguard-phase13-cost-state.json"]
    cleanup = values["tmp/archguard-phase13-evidence/cleanup.json"]
    cost = values["tmp/archguard-phase13-evidence/cost-state.json"]
    execution = values["tmp/archguard-phase13-evidence/execution-1.json"]
    manifest = values["tmp/archguard-phase13-evidence/manifest.json"]
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
    _validate_execution(execution)
    execution_hash = hashlib.sha256(canonical_json(execution)).hexdigest()
    if (
        cost.get("schema") != "archguard.phase-13-cost-state/v1"
        or cost.get("completed_primary") != 1
        or cost.get("calls_started") != 2
        or cost.get("observed_usd") != "0.025945"
        or manifest.get("schema") != "archguard.phase-13-manifest/v1"
        or manifest.get("completed_executions") != 1
        or manifest.get("total_calls") != 2
        or manifest.get("total_cost_usd") != "0.025945"
        or manifest.get("result_fingerprints") != [execution_hash]
    ):
        raise ValueError("imported incident evidence mismatch")


def _validate_execution(value: Any) -> None:
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
        != (1, "PySnooper-2", "PySnooper", "baseline")
        or value.get("terminal_classification") != "invalid_patch"
        or value.get("patch_parsed") is not False
        or value.get("patch_applied") is not False
        or value.get("evaluator_executed") is not False
        or value.get("observed_usd") != "0.025945"
        or value.get("usage")
        != {
            "cached_input_tokens": 0,
            "input_tokens": 5200,
            "output_tokens": 863,
            "reasoning_tokens": 0,
        }
        or any(
            not isinstance(value.get(key), str) or len(value[key]) != 64 for key in required_hashes
        )
    ):
        raise ValueError("imported execution mismatch")
    expected_cost = (
        Decimal("5200") * Decimal("2.50") + Decimal("863") * Decimal("15.00")
    ) / Decimal("1000000")
    if expected_cost != Decimal(value["observed_usd"]):
        raise ValueError("imported execution cost mismatch")
