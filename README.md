# ArchGuard-APR

Architecture-Constraint-Aware Multi-Agent Program Repair with Repository Graphs and Execution Feedback.

A research foundation for studying whether explicit architecture validation improves repository-level
repair. The research gap is preliminary and requires a verified literature review. No novelty,
repair effectiveness, benchmark performance or empirical result is claimed.

## Current implementation

Version 0.4.0 adds explicit versioned architecture profiles and deterministic conformance evaluation
against validated repository graphs. Four typed rules, canonical profile/report artifacts and CLI
workflows are implemented. Self-hosting CI checks ArchGuard's declared dependency boundaries.
Inference, patch comparison, LLM calls, agents and automated repair are **not implemented**.
Codex, Claude Code, MCP, IDE and GitHub Action product integrations remain **planned**.
No repair effectiveness or scientific performance result is claimed.

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
in Phase 4. Provider/model names are optional metadata. Application directories can be absolute;
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
docker build -t archguard-apr:phase-4 .
docker compose up --build
docker compose down
```

Targets: `install`, `format`, `lint`, `typecheck`, `test`, `test-cov`, `check`, `run`, `doctor`,
`docker-build`, `docker-up`, `docker-down`. Tests require at least 90% combined statement/branch coverage.
Containers run non-root and Compose binds localhost. No data services are included.
See [development](docs/development.md).

## Reproducibility and research roadmap

Record seeds, configuration and lock hashes, exact repository commits, environment/container
digests, model/provider versions and budgets. Preserve failed runs. Keep generated outputs and
benchmark checkouts out of Git and never expose gold patches to repair context.

1. Completed foundation: engineering and preliminary research protocol.
2. Completed: Phase 2 deterministic Python repository analysis.
3. Completed: Phase 3 deterministic repository graphs and structural queries.
4. Current: Phase 4 explicit architecture constraints and deterministic conformance.
5. Later: before/after validation, isolated execution and external-agent validation.
6. Later: separable multi-agent orchestration and controlled evaluation.

See [protocol](docs/research/research-protocol.md), [questions](docs/research/research-questions.md)
and [registry](docs/research/experiment-registry.md). Smoke configuration is metadata only.

## License and citation

Code: [Apache-2.0](LICENSE). Original documentation: [CC BY 4.0](docs/LICENSE.md).
Future original datasets may use CC BY 4.0 only where underlying rights permit; upstream
licenses remain controlling. Cite using [CITATION.cff](CITATION.cff). No DOI is assigned.

## Repository analysis (CLI and Python use case)

```bash
uv run archguard repository analyze examples/python/simple-layered-app --source-root src
uv run archguard repository analyze examples/python/simple-layered-app --config configs/app.example.yaml
uv run archguard repository analyze examples/python/simple-layered-app \
  --source-root src --output /tmp/archguard-analysis.json
uv run archguard repository inspect /tmp/archguard-analysis.json
# Optional integrity check: append --sha256 EXPECTED_SHA256 to inspect.
uv run python scripts/benchmark_repository_analysis.py
```

Output is a concise JSON summary with fingerprint, counts and complete/partial status. `--output`
writes canonical JSON externally and reports a basename and artifact hash. It cannot write inside
the analyzed repository. Source is parsed without importing or executing it; links are never followed.
Analysis requires Unix descriptor-relative APIs (macOS/Linux); unsupported platforms fail closed.
Use stable checkouts and output parents. `.gitignore` is not interpreted. HTTP analysis is not exposed.

`--source-root` is repeatable and explicitly overrides configured roots. Environment overrides YAML;
nested settings use `ARCHGUARD_ANALYSIS__MAX_FILE_BYTES=1048576`, or JSON array values for collections.
`--strict` fails on error diagnostics after safe reporting; `analysis.fail_fast` aborts immediately.
Exit codes: 0 complete/collected partial, 1 strict errors or I/O/analysis failure, 2 invalid input,
3 path-policy rejection. Any partial status must be considered when consuming research artifacts.
See [analysis policy](docs/architecture/repository-analysis.md), [schema](docs/schemas/repository-snapshot-v1.md)
and [ADR-0003](docs/architecture/decisions/ADR-0003-canonical-repository-snapshot.md).

## Repository graph CLI

```bash
uv run archguard repository analyze examples/python/simple-layered-app \
  --source-root src --output /tmp/archguard-snapshot.json
uv run archguard graph build /tmp/archguard-snapshot.json --output /tmp/archguard-graph.json
uv run archguard graph inspect /tmp/archguard-graph.json
uv run archguard graph node /tmp/archguard-graph.json module:demo.service
uv run archguard graph neighbors /tmp/archguard-graph.json module:demo.service --direction incoming
uv run archguard graph dependencies /tmp/archguard-graph.json module:demo.service
uv run archguard graph reverse-dependencies /tmp/archguard-graph.json module:demo.model
uv run archguard graph path /tmp/archguard-graph.json module:demo.controller module:demo.model
uv run archguard graph cycles /tmp/archguard-graph.json
uv run archguard graph cycles /tmp/archguard-graph.json --runtime-only
uv run python scripts/benchmark_repository_graph.py
```

Build reads only the snapshot. Supply `--protected-root SOURCE_ROOT` when repository context is known.
Queries return deterministic JSON; inspect supports `--sha256`. Neighbors and path accept `--kind`.
Exit codes: 0 success (including partial graphs), 1 artifact I/O failure, 2 invalid input/node,
3 path-policy rejection. No full graph is printed by default. See [graph policy](docs/architecture/repository-graph.md),
[schema](docs/schemas/repository-graph-v1.md), and [verification](docs/phase-3-verification.md).

## Architecture conformance CLI

```bash
uv run archguard repository analyze examples/python/simple-layered-app \
  --source-root src --output /tmp/archguard-snapshot.json
uv run archguard graph build /tmp/archguard-snapshot.json --output /tmp/archguard-graph.json
uv run archguard architecture profile validate examples/architecture/simple-layered.yaml
uv run archguard architecture profile compile examples/architecture/simple-layered.yaml \
  --output /tmp/archguard-profile.json
uv run archguard architecture profile inspect /tmp/archguard-profile.json
uv run archguard architecture evaluate /tmp/archguard-graph.json \
  --profile examples/architecture/simple-layered.yaml --output /tmp/archguard-report.json
uv run archguard architecture inspect /tmp/archguard-report.json
uv run archguard architecture violations /tmp/archguard-report.json
uv run archguard architecture violations /tmp/archguard-report.json --severity error
make architecture-self
uv run python scripts/benchmark_constraint_engine.py
```

The example profile passes. `simple-layered-violating.yaml` intentionally rejects the existing
application-to-persistence import; see the actual explanation command in
[Phase 4 verification](docs/phase-4-verification.md). Profiles are explicit specifications, not inferred
layers. Assignment ambiguity is never resolved by declaration order. Dependency violations aggregate
occurrences per rule/source/target; cycle violations aggregate per scoped SCC.

Exit codes: 0 passed/valid, 1 conformance failed, 2 invalid input or artifact I/O, 3 unsafe path,
4 partial evaluation without `--allow-partial`. A valid report is persisted before conformance exit.
Warnings do not fail. Partial status always remains visible. Supply `--protected-root ROOT` to protect
an analyzed root; inputs cannot be overwritten by compile/evaluate. Generated outputs belong outside
analyzed roots. Targets: `architecture-smoke`, `architecture-self`, `architecture-benchmark`.

Read the [DSL](docs/architecture/constraint-dsl.md), [engine](docs/architecture/constraint-engine.md),
[profile schema](docs/schemas/architecture-profile-v1.md),
[report schema](docs/schemas/architecture-report-v1.md) and
[ADR-0005](docs/architecture/decisions/ADR-0005-versioned-constraint-dsl.md).
