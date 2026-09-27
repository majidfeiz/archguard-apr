"""Strict trusted YAML execution-plan loading and canonical persistence."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml
from pydantic import TypeAdapter

from archguard.domain.canonical import canonical_json
from archguard.domain.execution import ExecutionPlan
from archguard.infrastructure.artifact_io import atomic_write, destination_path, read_artifact
from archguard.infrastructure.json_codec import unique_object

MAX_PLAN_BYTES = 256 * 1024


def canonical_plan(plan: ExecutionPlan) -> bytes:
    return canonical_json(asdict(plan))


class LocalExecutionPlans:
    def load(self, source: Path) -> ExecutionPlan:
        raw = read_artifact(source, None, MAX_PLAN_BYTES)
        try:
            data: Any
            if source.suffix.lower() in {".yaml", ".yml"}:
                data = yaml.safe_load(raw)
                if not isinstance(data, dict):
                    raise ValueError("plan must be an object")
                raw = canonical_json(data)
            else:
                data = json.loads(raw, object_pairs_hook=unique_object)
            plan = TypeAdapter(ExecutionPlan).validate_json(raw, strict=True)
            if (
                source.suffix.lower() not in {".yaml", ".yml"}
                and json.loads(canonical_plan(plan)) != data
            ):
                raise ValueError("noncanonical execution plan")
            return plan
        except (yaml.YAMLError, ValueError, TypeError, KeyError, RecursionError):
            raise ValueError("invalid execution plan") from None

    def write(self, plan: ExecutionPlan, destination: Path) -> None:
        atomic_write(destination_path(destination), canonical_plan(plan))
