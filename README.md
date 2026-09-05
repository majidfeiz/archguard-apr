# ArchGuard-APR

Architecture-Constraint-Aware Multi-Agent Program Repair with Repository Graphs and Execution Feedback.

A research foundation for studying whether explicit architecture validation improves repository-level
repair. The research gap is preliminary and requires a verified literature review. No novelty,
repair effectiveness, benchmark performance or empirical result is claimed.

## Current implementation

Phase 1 provides library values and ports, metadata CLI, health API, settings, logging, tests,
CI and a preliminary research protocol. Repository analysis, graph retrieval, constraint engines,
LLM calls, agents and automated repair are **not implemented**. Codex, Claude Code, MCP, IDE
and GitHub Action product integrations are **planned**. The existing workflow is development CI.

## Architecture and layout

Ports-and-adapters modular monolith: entrypoints → application → domain. Infrastructure implements
application ports. Core layers import only standard-library modules and domain values.

- `src/archguard/domain`: immutable provider-neutral values.
- `src/archguard/application/ports`: future capability contracts.
- `src/archguard/entrypoints`: Typer CLI and FastAPI factory.
- `src/archguard/infrastructure`: configuration, logging and path probes.
- `src/archguard/schemas`: boundary validation.
- `configs`, `docs`, `experiments`: examples, research and artifact policies.
- `tests`: unit, integration and architecture tests; `.github`: CI and templates.

See [architecture](docs/architecture/overview.md) and [integration strategy](docs/architecture/integration-strategy.md).

## Prerequisites and quick start

Python 3.12, uv and Git. Python 3.13 is supported; `.python-version` selects 3.12.
Docker is optional for library development and required for container checks.

```bash
uv sync --frozen
uv run archguard version
uv run archguard doctor
uv run archguard config show
uv run archguard config show --config configs/app.example.yaml
uv run archguard experiment validate --config configs/experiments/smoke.yaml
uv run uvicorn archguard.entrypoints.api.app:create_app --factory --host 127.0.0.1 --port 8000
```

API: `/health`, `/ready`, `/version`. Readiness means validated configuration, not execution-backend
availability. Imports perform no I/O or logging setup. Factory creation loads settings.
Doctor checks Python, settings, workspace, output writability and Git. Missing optional Docker
is reported without failing; daemon state is explicitly not checked. Failed prerequisites exit 1;
invalid configuration or metadata exits 2. Experiment validation never runs a benchmark.

## Configuration

Precedence: environment variables > current-directory `.env` > explicit YAML/constructor values >
defaults. Prefix: `ARCHGUARD_`. See `.env.example` and `configs/app.example.yaml`.
Unknown fields fail. No API key is required or reserved. Provider execution must remain false
in Phase 1. Provider/model names are optional metadata. Application directories can be absolute;
artifact and experiment output references must be relative POSIX paths without parent traversal.
Lexical path validation does not provide symlink containment or an execution sandbox.

## Quality and Docker

```bash
make install
make check
uv build
uv run pre-commit install
uv run pre-commit run --all-files
docker compose config
docker build -t archguard-apr:phase-1 .
docker compose up --build
docker compose down
```

Targets: `install`, `format`, `lint`, `typecheck`, `test`, `test-cov`, `check`, `run`, `doctor`,
`docker-build`, `docker-up`, `docker-down`. Tests require at least 85% source coverage.
Containers run non-root and Compose binds localhost. No data services are included.
See [development](docs/development.md).

## Reproducibility and research roadmap

Record seeds, configuration and lock hashes, exact repository commits, environment/container
digests, model/provider versions and budgets. Preserve failed runs. Keep generated outputs and
benchmark checkouts out of Git and never expose gold patches to repair context.

1. Current: Phase 1 engineering and preliminary research protocol.
2. Later: verified literature, dataset/license selection, repository analysis and graphs.
3. Later: architecture constraints, isolated execution and external-agent validation.
4. Later: separable multi-agent orchestration and controlled evaluation.

See [protocol](docs/research/research-protocol.md), [questions](docs/research/research-questions.md)
and [registry](docs/research/experiment-registry.md). Smoke configuration is metadata only.

## License and citation

Code: [Apache-2.0](LICENSE). Original documentation: [CC BY 4.0](docs/LICENSE.md).
Future original datasets may use CC BY 4.0 only where underlying rights permit; upstream
licenses remain controlling. Cite using [CITATION.cff](CITATION.cff). No DOI is assigned.
