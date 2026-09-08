"""Narrow boundaries required by isolated candidate validation."""

from contextlib import AbstractContextManager
from pathlib import Path
from typing import Protocol

from archguard.domain.patch_validation import (
    CandidatePatch,
    PatchValidationResult,
    RepositoryStateProof,
)


class CandidatePatchInspectorPort(Protocol):
    def inspect(
        self, raw: bytes, allowed_roots: tuple[str, ...] = (), protected_paths: tuple[str, ...] = ()
    ) -> CandidatePatch: ...


class RepositoryStatePort(Protocol):
    def resolve_commit(self, repository: Path, revision: str) -> str: ...
    def capture(self, repository: Path) -> RepositoryStateProof: ...


class CandidateWorkspacePort(Protocol):
    def workspace(self, repository: Path, baseline_commit: str) -> AbstractContextManager[Path]: ...
    def check_apply(self, workspace: Path, raw: bytes) -> bool: ...
    def apply(self, workspace: Path, raw: bytes) -> bool: ...


class PatchValidationArtifactPort(Protocol):
    def write(self, result: PatchValidationResult, destination: Path) -> None: ...
    def read(self, source: Path, expected_sha256: str | None = None) -> PatchValidationResult: ...
