"""External storage containment checks; no acquisition or execution."""

from pathlib import Path


def validate_external_root(candidate: Path, repository: Path) -> Path:
    if not candidate.is_absolute():
        raise ValueError("benchmark storage must be absolute")
    resolved_repository = repository.resolve(strict=True)
    resolved_candidate = candidate.resolve(strict=False)
    if (
        resolved_candidate == resolved_repository
        or resolved_repository in resolved_candidate.parents
    ):
        raise ValueError("benchmark storage cannot be inside repository")
    if candidate.exists() and candidate.is_symlink():
        raise ValueError("benchmark storage root cannot be a symlink")
    return resolved_candidate
