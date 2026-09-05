# ADR-0002: Python tooling

Status: Accepted.

Context: Research requires repeatable installs and auditable quality gates.
Decision: Python 3.12 with 3.13 support, uv.lock, src layout, Pydantic boundaries, standard-library
logging/domain, Typer CLI, FastAPI health API, strict mypy, Ruff and pytest with branch measurement
and at least 85% coverage.
Consequences: CI checks both minor versions. Review lock updates. Docker fixes uv version and
uses frozen installs; record base-image digests for research releases because tags can change.
