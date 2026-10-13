"""Canonical allowlisted source-free Phase 13 persistence."""

import json
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from archguard.domain.canonical import canonical_json
from archguard.domain.phase13 import (
    PROVIDER_FINGERPRINT,
    ExecutionResult,
    PreProviderDiagnostic,
)
from archguard.infrastructure.artifact_io import atomic_write

ALLOWLIST = frozenset(
    {
        "cleanup.json",
        "cost-state.json",
        "manifest.json",
        "pre-provider-failure.json",
        *(f"execution-{index}.json" for index in range(1, 7)),
    }
)
FORBIDDEN_KEYS = frozenset(
    {
        "api_key",
        "command",
        "environment",
        "evaluator_source",
        "patch",
        "prompt",
        "response",
        "stderr",
        "stdout",
    }
)


class SourceFreeArtifacts:
    def __init__(self, root: Path) -> None:
        if root.exists():
            raise FileExistsError("output directory already exists")
        root.mkdir(parents=True, mode=0o700)
        self.root = root

    def write_cost_state(self, value: object) -> None:
        normalized = _normalize(value)
        if not isinstance(normalized, dict):
            raise ValueError("invalid cost state")
        observed = Decimal(str(normalized.get("observed_usd", "0")))
        reserved = Decimal(str(normalized.get("reserved_usd", "0")))
        self._write(
            "cost-state.json",
            {
                "schema": "archguard.phase-13-cost-state/v1",
                **normalized,
                "remaining_internal_budget_usd": str(
                    max(Decimal("0"), Decimal("4.50") - observed - reserved)
                ),
                "provider_configuration_fingerprint": PROVIDER_FINGERPRINT,
            },
        )

    def write_result(self, result: ExecutionResult) -> None:
        self._write(f"execution-{result.identity.ordinal}.json", result.source_free_record())

    def write_imported_result(self, ordinal: int, value: object) -> None:
        self._write(f"execution-{ordinal}.json", value)

    def write_manifest(self, value: object) -> None:
        self._write("manifest.json", value)

    def write_cleanup(self, value: object) -> None:
        self._write("cleanup.json", value)

    def write_pre_provider_diagnostic(self, value: PreProviderDiagnostic) -> None:
        self._write("pre-provider-failure.json", value)

    def _write(self, name: str, value: object) -> None:
        if name not in ALLOWLIST:
            raise ValueError("artifact is not allowlisted")
        normalized = _normalize(value)
        _reject_sensitive(normalized)
        atomic_write(self.root / name, canonical_json(normalized))


def _normalize(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _normalize(asdict(value))
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalize(item) for item in value]
    return value


def _reject_sensitive(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in FORBIDDEN_KEYS:
                raise ValueError("source-bearing artifact field rejected")
            _reject_sensitive(item)
    elif isinstance(value, list):
        for item in value:
            _reject_sensitive(item)
    elif isinstance(value, str):
        if "sk-" in value or value.startswith("/") or "BEGIN PRIVATE" in value:
            raise ValueError("sensitive artifact value rejected")


def validate_artifact_directory(root: Path) -> None:
    files = {path.name for path in root.iterdir() if path.is_file()}
    if not files <= ALLOWLIST:
        raise ValueError("unknown Phase 13 artifact")
    for path in root.iterdir():
        if path.is_symlink() or not path.is_file():
            raise ValueError("unsafe Phase 13 artifact")
        _reject_sensitive(json.loads(path.read_text(encoding="utf-8")))
