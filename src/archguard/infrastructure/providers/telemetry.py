"""Source-free canonical provider invocation artifacts."""

from dataclasses import asdict
from pathlib import Path

from archguard.domain.canonical import canonical_json
from archguard.domain.providers import ProviderInvocation
from archguard.infrastructure.artifact_io import atomic_write, destination_path


def write_invocation(path: Path, invocation: ProviderInvocation) -> None:
    atomic_write(destination_path(path), canonical_json(asdict(invocation)))
