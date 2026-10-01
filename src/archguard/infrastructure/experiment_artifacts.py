"""Strict experiment artifact loading and immutable canonical persistence."""

import json
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import TypeAdapter, ValidationError

from archguard.domain.canonical import canonical_json
from archguard.infrastructure.artifact_io import atomic_write, destination_path

MAX_EXPERIMENT_ARTIFACT_BYTES = 8 * 1024 * 1024


def load_experiment_artifact[T](path: Path, kind: type[T]) -> T:
    raw = path.read_bytes()
    if len(raw) > MAX_EXPERIMENT_ARTIFACT_BYTES:
        raise ValueError("experiment artifact too large")
    try:
        data = yaml.safe_load(raw) if path.suffix.lower() in {".yaml", ".yml"} else json.loads(raw)
        if not isinstance(data, dict) or set(data) - {
            field.name for field in fields(cast(Any, kind))
        }:
            raise ValueError("unknown experiment artifact field")
        return TypeAdapter(kind).validate_python(data)
    except (yaml.YAMLError, json.JSONDecodeError, ValidationError, ValueError, TypeError):
        raise ValueError("invalid experiment artifact") from None


def write_experiment_artifact(path: Path, value: Any) -> None:
    target = destination_path(path)
    if target.exists():
        raise FileExistsError("immutable experiment artifact exists")
    atomic_write(target, canonical_json(asdict(value)))
