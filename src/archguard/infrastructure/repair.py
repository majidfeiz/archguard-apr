"""Strict repair-task loading, candidate construction, and canonical artifacts."""

import json
from dataclasses import asdict, fields
from pathlib import Path

import yaml
from pydantic import TypeAdapter, ValidationError

from archguard.domain.canonical import canonical_json
from archguard.domain.orchestration import AgentRole, ArtifactReference
from archguard.domain.repair import (
    PATCH_CANDIDATE_SCHEMA,
    CandidateLineage,
    PatchCandidate,
    RepairIntent,
    RepairResult,
    RepairTask,
    normalized_patch,
    patch_stats,
    raw_fingerprint,
    semantic_candidate_fingerprint,
)
from archguard.infrastructure.artifact_io import atomic_write, destination_path
from archguard.infrastructure.patch_inspector import UnifiedDiffInspector

MAX_TASK_BYTES = 1024 * 1024


def load_repair_task(path: Path) -> RepairTask:
    raw = path.read_bytes()
    if len(raw) > MAX_TASK_BYTES:
        raise ValueError("repair task is too large")
    try:
        data = yaml.safe_load(raw) if path.suffix.lower() in {".yaml", ".yml"} else json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("repair task must be an object")
        if set(data) - {field.name for field in fields(RepairTask)}:
            raise ValueError("repair task contains unknown fields")
        return TypeAdapter(RepairTask).validate_python(data)
    except (yaml.YAMLError, json.JSONDecodeError, ValidationError, ValueError, TypeError):
        raise ValueError("invalid repair task") from None


def make_candidate(
    *,
    task: RepairTask,
    run_id: str,
    candidate_id: str,
    repair_round: int,
    parent_candidate_id: str | None,
    role: AgentRole,
    provider_invocation: ArtifactReference,
    raw_patch_reference: ArtifactReference,
    raw: bytes,
    intent: RepairIntent,
    assumptions: tuple[str, ...] = (),
) -> tuple[PatchCandidate, bytes]:
    normalized = normalized_patch(raw)
    if len(normalized) > task.patch_policy.maximum_patch_bytes:
        raise ValueError("patch exceeds configured byte limit")
    parsed = UnifiedDiffInspector().inspect(normalized)
    if not parsed.acceptable:
        raise ValueError("patch parsing rejected")
    added, deleted = patch_stats(normalized)
    normalized_fingerprint = raw_fingerprint(normalized)
    paths = parsed.changed_paths
    candidate = PatchCandidate(
        PATCH_CANDIDATE_SCHEMA,
        candidate_id,
        run_id,
        task.task_fingerprint,
        repair_round,
        parent_candidate_id,
        role,
        provider_invocation,
        raw_patch_reference,
        normalized_fingerprint,
        semantic_candidate_fingerprint(task.task_fingerprint, normalized_fingerprint, paths),
        paths,
        added,
        deleted,
        intent,
        tuple(assumptions),
    )
    return candidate, normalized


class RepairArtifacts:
    def write_task(self, path: Path, task: RepairTask) -> None:
        self._write_new(path, task)

    def write_lineage(self, path: Path, lineage: CandidateLineage) -> None:
        self._write_new(path, lineage)

    def write_result(self, path: Path, result: RepairResult) -> None:
        self._write_new(path, result)

    @staticmethod
    def _write_new(path: Path, value: RepairTask | CandidateLineage | RepairResult) -> None:
        target = destination_path(path)
        if target.exists():
            raise FileExistsError("immutable repair artifact exists")
        atomic_write(target, canonical_json(asdict(value)))
