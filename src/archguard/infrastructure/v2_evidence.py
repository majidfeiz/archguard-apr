"""Canonical, flat, source-free V2.2 checkpoints and evidence archives."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import zipfile
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import cast

from archguard.application.ports.v2_execution import CheckpointStore
from archguard.domain.canonical import canonical_json
from archguard.domain.providers import ProviderResponseState
from archguard.domain.v2_execution import (
    BudgetLedger,
    ExecutionIdentity,
    ExecutionResult,
    ExecutionStatus,
    ProviderFailureDiagnostic,
    ProviderFailureKind,
    ProviderFailureRecord,
    StageStatus,
    TerminalClassification,
)
from archguard.infrastructure.artifact_io import atomic_write
from archguard.infrastructure.json_codec import unique_object

SCHEMA = "archguard.v2-micro-pilot-checkpoint/v2"
EVIDENCE_ALLOWLIST = frozenset(
    {
        "run-manifest.json",
        "aggregate-result.json",
        "cost-token-ledger.json",
        "fairness-report.json",
        "attrition-report.json",
        "checkpoint.json",
        "cleanup-report.json",
        "SHA256SUMS",
    }
    | {f"execution-{ordinal:02d}.json" for ordinal in range(1, 9)}
)
FORBIDDEN_KEYS = re.compile(
    r"^(api.?key|prompt|raw(_provider)?_response|response_body|patch_body|unified_diff|"
    r"source_code|repository_source|gold_material|environment_dump|local.?path)$",
    re.I,
)
SECRET = re.compile(rb"(?<![A-Za-z])sk-[A-Za-z0-9_-]{20,}")


def _integer(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("expected checkpoint integer")
    return value


def _plain(value: object) -> object:
    if isinstance(value, Decimal):
        return format(value, "f")
    if hasattr(value, "value"):
        return cast(object, value.value)
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def result_value(result: ExecutionResult) -> dict[str, object]:
    return cast(dict[str, object], _plain(asdict(result)))


def checkpoint_value(
    ledger: BudgetLedger,
    results: tuple[ExecutionResult, ...],
    failures: tuple[ProviderFailureRecord, ...],
    *,
    carried_calls: int = 0,
) -> dict[str, object]:
    if not 0 <= carried_calls <= ledger.provider_request_attempts:
        raise ValueError("invalid carried call count")
    value: dict[str, object] = {
        "schema": SCHEMA,
        "ledger": _plain(asdict(ledger)),
        "results": [result_value(item) for item in results],
        "provider_failures": [_plain(asdict(item)) for item in failures],
        "carried_calls": carried_calls,
        "new_provider_request_attempts": ledger.provider_request_attempts - carried_calls,
        "provider_request_attempts": ledger.provider_request_attempts,
        "accepted_provider_calls": ledger.accepted_provider_calls,
        "completed_calls": ledger.completed_calls,
        "infrastructure_failures": ledger.infrastructure_failures,
        "remaining_calls": ledger.remaining_calls,
        "remaining_provider_requests": ledger.remaining_provider_requests,
    }
    value["fingerprint"] = hashlib.sha256(canonical_json(value)).hexdigest()
    return value


class AtomicCheckpointStore(CheckpointStore):
    def __init__(self, path: Path, carried_calls: int = 0) -> None:
        self.path = path
        self.carried_calls = carried_calls

    def write(
        self,
        ledger: BudgetLedger,
        results: tuple[ExecutionResult, ...],
        failures: tuple[ProviderFailureRecord, ...],
    ) -> None:
        atomic_write(
            self.path,
            canonical_json(
                checkpoint_value(ledger, results, failures, carried_calls=self.carried_calls)
            ),
        )


def load_checkpoint(
    path: Path,
) -> tuple[BudgetLedger, tuple[ExecutionResult, ...], tuple[ProviderFailureRecord, ...]]:
    raw = path.read_bytes()
    value = json.loads(raw, object_pairs_hook=unique_object)
    if not isinstance(value, dict) or canonical_json(value) != raw:
        raise ValueError("checkpoint is not canonical")
    fingerprint = value.get("fingerprint")
    unsigned = {key: item for key, item in value.items() if key != "fingerprint"}
    if fingerprint != hashlib.sha256(canonical_json(unsigned)).hexdigest():
        raise ValueError("checkpoint fingerprint mismatch")
    if value.get("schema") != SCHEMA or not isinstance(value.get("ledger"), dict):
        raise ValueError("invalid checkpoint schema")
    ledger_data = cast(dict[str, object], value["ledger"])
    ledger = BudgetLedger(
        completed_ordinals=tuple(
            _integer(item) for item in cast(list[object], ledger_data["completed_ordinals"])
        ),
        failed_attempt_ordinals=tuple(
            _integer(item) for item in cast(list[object], ledger_data["failed_attempt_ordinals"])
        ),
        provider_request_attempts=_integer(ledger_data["provider_request_attempts"]),
        accepted_provider_calls=_integer(ledger_data["accepted_provider_calls"]),
        infrastructure_failures=_integer(ledger_data["infrastructure_failures"]),
        in_flight_ordinal=cast(int | None, ledger_data["in_flight_ordinal"]),
        observed_cost_usd=Decimal(str(ledger_data["observed_cost_usd"])),
        reserved_cost_usd=Decimal(str(ledger_data["reserved_cost_usd"])),
    )
    results = tuple(_decode_result(cast(dict[str, object], item)) for item in value["results"])
    failures = tuple(
        _decode_failure(cast(dict[str, object], item)) for item in value["provider_failures"]
    )
    if tuple(item.identity.ordinal for item in results) != ledger.completed_ordinals:
        raise ValueError("checkpoint results contradict ledger")
    if tuple(item.identity.ordinal for item in failures) != ledger.failed_attempt_ordinals:
        raise ValueError("checkpoint failures contradict ledger")
    return ledger, results, failures


def _decode_result(value: dict[str, object]) -> ExecutionResult:
    identity = cast(dict[str, object], value["identity"])
    return ExecutionResult(
        ExecutionIdentity(
            _integer(identity["ordinal"]), str(identity["task_id"]), str(identity["condition"])
        ),
        ExecutionStatus(str(value["status"])),
        _integer(value["accepted_provider_call_count"]),
        _integer(value["input_tokens"]),
        _integer(value["output_tokens"]),
        Decimal(str(value["observed_cost_usd"])),
        Decimal(str(value["reserved_cost_usd"])),
        StageStatus(str(value["patch_extraction"])),
        StageStatus(str(value["validation"])),
        StageStatus(str(value["sandbox_evaluation"])),
        StageStatus(str(value["architecture_evaluation"])),
        TerminalClassification(str(value["terminal_classification"])),
        tuple(str(item) for item in cast(list[object], value["diagnostic_fingerprints"])),
        ProviderResponseState(str(value.get("response_state", "COMPLETED"))),
    )


def _decode_failure(value: dict[str, object]) -> ProviderFailureRecord:
    identity = cast(dict[str, object], value["identity"])
    diagnostic = cast(dict[str, object], value["diagnostic"])
    return ProviderFailureRecord(
        ExecutionIdentity(
            _integer(identity["ordinal"]), str(identity["task_id"]), str(identity["condition"])
        ),
        ProviderFailureDiagnostic(
            ProviderFailureKind(str(diagnostic["kind"])),
            str(diagnostic["stage"]),
            bool(diagnostic["retryable"]),
            cast(int | None, diagnostic["http_status"]),
            cast(str | None, diagnostic["provider_code"]),
            bool(diagnostic["usage_returned"]),
            cast(str | None, diagnostic["request_id_hash"]),
            str(diagnostic["fingerprint"]),
        ),
        _integer(value["accepted_provider_call_count"]),
        _integer(value["input_tokens"]),
        _integer(value["output_tokens"]),
        Decimal(str(value["observed_cost_usd"])),
        ProviderResponseState(str(value.get("response_state", "NOT_RECEIVED"))),
    )


def validate_source_free(value: object) -> None:
    def walk(item: object) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if FORBIDDEN_KEYS.search(str(key)):
                    raise ValueError(f"forbidden evidence field: {key}")
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)
        elif isinstance(item, str):
            raw = item.encode()
            if SECRET.search(raw) or "BEGIN " in item or "diff --git" in item:
                raise ValueError("sensitive evidence content rejected")

    walk(value)


def build_evidence_archive(directory: Path, output: Path) -> None:
    files = sorted(path for path in directory.iterdir() if path.is_file())
    names = {path.name for path in files}
    if not names <= EVIDENCE_ALLOWLIST or "checkpoint.json" not in names:
        raise ValueError("evidence file allowlist violation")
    for path in files:
        if path.name.endswith(".json"):
            value = json.loads(path.read_bytes(), object_pairs_hook=unique_object)
            validate_source_free(value)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            info = zipfile.ZipInfo(path.name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())


def write_run_evidence(
    directory: Path,
    ledger: BudgetLedger,
    results: tuple[ExecutionResult, ...],
    failures: tuple[ProviderFailureRecord, ...],
    *,
    protocol_fingerprint: str,
    fairness_fingerprint: str,
    cleanup_complete: bool,
    carried_calls: int = 0,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    documents: dict[str, object] = {
        "run-manifest.json": {
            "schema": "archguard.v2-micro-pilot-run/v1",
            "protocol_fingerprint": protocol_fingerprint,
            "execution_count": len(results),
            "provider_request_attempts": ledger.provider_request_attempts,
            "accepted_provider_calls": ledger.accepted_provider_calls,
            "infrastructure_failures": ledger.infrastructure_failures,
        },
        "aggregate-result.json": {
            "schema": "archguard.v2-micro-pilot-aggregate/v1",
            "classifications": {
                classification.value: sum(
                    item.terminal_classification is classification for item in results
                )
                for classification in TerminalClassification
            },
            "completed": len(results),
        },
        "cost-token-ledger.json": {
            "schema": "archguard.v2-cost-token-ledger/v1",
            "completed_calls": ledger.completed_calls,
            "provider_request_attempts": ledger.provider_request_attempts,
            "accepted_provider_calls": ledger.accepted_provider_calls,
            "infrastructure_failures": ledger.infrastructure_failures,
            "remaining_calls": ledger.remaining_calls,
            "remaining_provider_requests": ledger.remaining_provider_requests,
            "observed_cost_usd": format(ledger.observed_cost_usd, "f"),
            "reserved_cost_usd": format(ledger.reserved_cost_usd, "f"),
            "input_tokens": sum(item.input_tokens for item in results),
            "output_tokens": sum(item.output_tokens for item in results),
        },
        "fairness-report.json": {
            "schema": "archguard.v2-fairness-report/v1",
            "fingerprint": fairness_fingerprint,
            "status": "FAIR",
            "unintended_differences": [],
        },
        "attrition-report.json": {
            "schema": "archguard.v2-attrition/v1",
            "scheduled": 8,
            "completed": len(results),
            "remaining": 8 - len(results),
        },
        "checkpoint.json": checkpoint_value(ledger, results, failures, carried_calls=carried_calls),
        "cleanup-report.json": {
            "schema": "archguard.v2-cleanup/v1",
            "complete": cleanup_complete,
        },
    }
    for result in results:
        documents[f"execution-{result.identity.ordinal:02d}.json"] = result_value(result)
    for name, value in documents.items():
        validate_source_free(value)
        atomic_write(directory / name, canonical_json(value))
    sums = "".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
        for path in sorted(directory.iterdir())
        if path.is_file() and path.name != "SHA256SUMS"
    ).encode()
    atomic_write(directory / "SHA256SUMS", sums)
    archive = directory.parent / "v2-micro-pilot-evidence.zip"
    build_evidence_archive(directory, archive)
    return archive


def import_evidence(archive_path: Path, directory: Path) -> None:
    if directory.is_symlink() or not directory.is_dir() or any(directory.iterdir()):
        raise ValueError("resume destination must be an empty non-symlink directory")
    members: dict[str, bytes] = {}
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or not set(names) <= EVIDENCE_ALLOWLIST:
            raise ValueError("archive allowlist violation")
        if "checkpoint.json" not in names or "SHA256SUMS" not in names:
            raise ValueError("archive is missing required resume evidence")
        if any("/" in name or "\\" in name for name in names):
            raise ValueError("archive must be flat")
        for info in archive.infolist():
            if (info.external_attr >> 16) & 0o170000 not in {0, 0o100000}:
                raise ValueError("non-regular archive member")
            if info.file_size > 16 * 1024 * 1024:
                raise ValueError("archive member exceeds size limit")
            raw = archive.read(info)
            if info.filename.endswith(".json"):
                validate_source_free(json.loads(raw, object_pairs_hook=unique_object))
            members[info.filename] = raw
    checksummed: set[str] = set()
    for line in members["SHA256SUMS"].decode("ascii").splitlines():
        expected, name = line.split("  ", 1)
        if name in checksummed or name not in members or name == "SHA256SUMS":
            raise ValueError("invalid checksum member")
        checksummed.add(name)
        if hashlib.sha256(members[name]).hexdigest() != expected:
            raise ValueError("evidence checksum mismatch")
    if checksummed != set(members) - {"SHA256SUMS"}:
        raise ValueError("incomplete evidence checksums")
    with tempfile.TemporaryDirectory(prefix="archguard-v2-import-") as temporary:
        checkpoint = Path(temporary) / "checkpoint.json"
        checkpoint.write_bytes(members["checkpoint.json"])
        load_checkpoint(checkpoint)
    for name, raw in sorted(members.items()):
        target = directory / name
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as file:
            file.write(raw)
