"""Canonical run persistence and deterministic scripted agents."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml
from pydantic import TypeAdapter

from archguard.domain.canonical import canonical_json
from archguard.domain.orchestration import (
    AgentRequest,
    AgentResponse,
    HumanDecision,
    RepairCheckpoint,
    RepairRunSpec,
    RunEvent,
)
from archguard.infrastructure.artifact_io import atomic_write, destination_path, read_artifact
from archguard.infrastructure.json_codec import unique_object

MAX_RUN_ARTIFACT_BYTES = 16 * 1024 * 1024


class ScriptedAgent:
    """Returns predeclared responses and performs no I/O or execution."""

    def __init__(self, responses: tuple[AgentResponse, ...]) -> None:
        self.responses = responses
        self.invocations = 0

    def invoke(self, request: AgentRequest) -> AgentResponse:
        if self.invocations >= len(self.responses):
            raise RuntimeError("scripted response exhausted")
        response = self.responses[self.invocations]
        self.invocations += 1
        return response


def _plain(value: Any) -> object:
    if isinstance(value, tuple):
        return [asdict(item) for item in value]
    return asdict(value)


def _decode[T](raw: bytes, cls: type[T]) -> T:
    try:
        data = json.loads(raw, object_pairs_hook=unique_object)
        value = TypeAdapter(cls).validate_json(raw, strict=True)
        if json.loads(canonical_json(_plain(value))) != data:
            raise ValueError("noncanonical artifact")
        return value
    except (ValueError, TypeError, KeyError, RecursionError):
        raise ValueError("invalid orchestration artifact") from None


class LocalRunArtifacts:
    def load_spec(self, source: Path) -> RepairRunSpec:
        raw = read_artifact(source, None, MAX_RUN_ARTIFACT_BYTES)
        if source.suffix.lower() in {".yaml", ".yml"}:
            try:
                data = yaml.safe_load(raw)
                if not isinstance(data, dict):
                    raise ValueError("spec must be an object")
                raw = canonical_json(data)
                return TypeAdapter(RepairRunSpec).validate_json(raw, strict=True)
            except (yaml.YAMLError, ValueError, TypeError):
                raise ValueError("invalid run specification") from None
        return _decode(raw, RepairRunSpec)

    def write_run(
        self,
        directory: Path,
        spec: RepairRunSpec,
        events: tuple[RunEvent, ...],
        checkpoint: RepairCheckpoint,
    ) -> None:
        if directory.exists():
            raise FileExistsError("immutable run directory already exists")
        directory.mkdir(parents=False)
        for name, value in (
            ("spec.json", spec),
            ("events.json", events),
            ("checkpoint.json", checkpoint),
        ):
            atomic_write(destination_path(directory / name), canonical_json(_plain(value)))

    def read_run(
        self, directory: Path
    ) -> tuple[RepairRunSpec, tuple[RunEvent, ...], RepairCheckpoint]:
        spec = _decode(
            read_artifact(directory / "spec.json", None, MAX_RUN_ARTIFACT_BYTES), RepairRunSpec
        )
        events = _decode(
            read_artifact(directory / "events.json", None, MAX_RUN_ARTIFACT_BYTES),
            tuple[RunEvent, ...],
        )
        checkpoint = _decode(
            read_artifact(directory / "checkpoint.json", None, MAX_RUN_ARTIFACT_BYTES),
            RepairCheckpoint,
        )
        return spec, events, checkpoint

    def write_decision(self, directory: Path, decision: HumanDecision) -> None:
        target = destination_path(directory / "human-decision.json")
        if target.exists():
            raise FileExistsError("immutable human decision already exists")
        atomic_write(target, canonical_json(asdict(decision)))
