"""Strict benchmark manifests, safe cache verification, and canonical persistence."""

import hashlib
import json
from dataclasses import asdict, fields
from pathlib import Path

import yaml
from pydantic import TypeAdapter, ValidationError

from archguard.domain.benchmark import BenchmarkRegistry, BenchmarkSnapshot
from archguard.domain.canonical import canonical_json
from archguard.infrastructure.artifact_io import atomic_write, destination_path

MAX_MANIFEST_BYTES = 4 * 1024 * 1024
CACHE_MARKER = "archguard-cache-complete.json"


def _load(
    path: Path, kind: type[BenchmarkRegistry] | type[BenchmarkSnapshot]
) -> BenchmarkRegistry | BenchmarkSnapshot:
    raw = path.read_bytes()
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError("benchmark manifest too large")
    try:
        data = yaml.safe_load(raw) if path.suffix.lower() in {".yaml", ".yml"} else json.loads(raw)
        if not isinstance(data, dict) or set(data) - {field.name for field in fields(kind)}:
            raise ValueError("unknown benchmark manifest field")
        return TypeAdapter(kind).validate_python(data)
    except (yaml.YAMLError, json.JSONDecodeError, ValidationError, ValueError, TypeError):
        raise ValueError("invalid benchmark manifest") from None


def load_registry(path: Path) -> BenchmarkRegistry:
    value = _load(path, BenchmarkRegistry)
    assert isinstance(value, BenchmarkRegistry)
    return value


def load_snapshot(path: Path) -> BenchmarkSnapshot:
    value = _load(path, BenchmarkSnapshot)
    assert isinstance(value, BenchmarkSnapshot)
    return value


def write_canonical(path: Path, value: BenchmarkRegistry | BenchmarkSnapshot) -> str:
    target = destination_path(path)
    if target.exists():
        raise FileExistsError("immutable benchmark artifact exists")
    raw = canonical_json(asdict(value))
    atomic_write(target, raw)
    return hashlib.sha256(raw).hexdigest()


def verify_cache(cache: Path) -> dict[str, object]:
    marker = cache / CACHE_MARKER
    if not cache.is_dir() or not marker.is_file():
        raise ValueError("incomplete benchmark cache")
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise ValueError("corrupted benchmark cache marker") from None
    if (
        not isinstance(data, dict)
        or set(data) != {"schema", "files"}
        or data["schema"] != "archguard.benchmark-cache/v1"
        or not isinstance(data["files"], list)
    ):
        raise ValueError("invalid benchmark cache marker")
    checked = 0
    for item in data["files"]:
        if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
            raise ValueError("invalid benchmark cache entry")
        relative = Path(str(item["path"]))
        if relative.is_absolute() or ".." in relative.parts or relative.name == CACHE_MARKER:
            raise ValueError("unsafe benchmark cache path")
        payload = cache / relative
        if (
            not payload.is_file()
            or hashlib.sha256(payload.read_bytes()).hexdigest() != item["sha256"]
        ):
            raise ValueError("benchmark cache checksum mismatch")
        checked += 1
    return {"status": "verified", "file_count": checked, "network_access": False}
