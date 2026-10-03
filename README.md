# ArchGuard-APR

Architecture-Constraint-Aware Multi-Agent Program Repair with Repository Graphs and Execution Feedback.

A research foundation for studying whether explicit architecture validation improves repository-level
repair. The research gap is preliminary and requires a verified literature review. No novelty,
repair effectiveness, benchmark performance or empirical result is claimed.

## Current implementation

Version 0.12.8 adds fail-closed Phase 12.7 evidence ingestion, human review and protocol-freeze
contracts, deterministic representative-task selection policy, and a factual Phase 13 readiness gate.
Phase 12.8A additionally prepares separately scoped license evidence, revision/profile-bound graph
evidence, outcome-blind pilot selection, and prospective power scenarios; external execution and human
review remain required.
Human decisions remain pending and no Phase 13 experiment is run. Version 0.12.6 added a strict
low-resource local micro-pilot: two real BugsInPy tasks were attempted,
one stable task/evaluator qualified, and its architecture profile remains review-required. No paid
provider or SWE-bench task ran, and Phase 13 remains blocked. Version 0.12.5 added external benchmark onboarding controls, source allowlists, external storage
containment, license/reproduction/profile-review records, gold quarantine scans and non-forgeable
Phase 13 readiness. Official metadata revisions were inspected, but no real task was qualified and
Phase 13 remains blocked. Version 0.12.0 added controlled baseline and one-factor ablation definitions, comparison fairness,
deterministic randomized-block scheduling, source-free run metrics and ledgers, blinding, descriptive
pilot summaries, and an offline repeated experiment fixture. No live pilot or final scientific
experiment was run. Version 0.11.0 added an immutable benchmark metadata pipeline, deterministic eligibility and splits,
verified offline caches, gold quarantine boundaries, and source-free fixtures. It supports BugsInPy
and SWE-bench Verified metadata shapes, but no external instance was acquired or verified. Version
0.10.0 added deterministic iterative multi-candidate repair-loop contracts, protected prechecks,
lineage, feedback and evidence-only selection. Version 0.9.0 added secure OpenAI Responses
and Anthropic Messages adapters. Version 0.8.0 added
provider-neutral typed repair orchestration, bounded budgets, hash-chained events,
verified checkpoints, deterministic replay/ranking, scripted agents and explicit human gates.
Version 0.7.0 added Docker-only execution feedback, trusted digest-pinned plans, pytest/JUnit evidence,
deterministic functional deltas and combined architecture/functional gates. Version 0.6.0 added
deterministic graph-based context retrieval, source-free manifests, explicitly
sensitive bounded source bundles, and offline retrieval evaluation. Version 0.5.0 added isolated
candidate patch validation and deterministic before/after architecture
comparison. Version 0.4.0 added explicit versioned architecture profiles and conformance evaluation
against validated repository graphs. Four typed rules, canonical profile/report artifacts and CLI
workflows are implemented. Self-hosting CI checks ArchGuard's declared dependency boundaries.
Phase 9 adds secure direct OpenAI Responses and Anthropic Messages API adapters with offline contract
tests. Provider inference is nondeterministic and no repair-performance result is claimed. Codex CLI,
Claude Code, MCP, IDE and GitHub Action product integrations remain **planned**.
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
uv run archguard experiment plan validate --plan configs/experiments/phase12-plan.yaml
uv run archguard benchmark external preflight \
  --registry configs/benchmarks.external-metadata.yaml --output /tmp/external-preflight.json
uv run uvicorn archguard.entrypoints.api.app:create_app --factory --host 127.0.0.1 --port 8000
```

Validate a trusted plan without executing candidate code:

```bash
uv run archguard execution plan validate --plan examples/execution/archguard-self.yaml
```

Execution comparison never falls back to a host subprocess. See
[execution feedback](docs/architecture/execution-feedback.md).

API: `/health`, `/ready`, `/version`. Readiness means validated configuration, not execution-backend
availability. Imports perform no I/O or logging setup. Factory creation loads settings.
Doctor checks Python, settings, workspace, output writability and Git. Missing optional Docker
is reported without failing; daemon state is explicitly not checked. Failed prerequisites exit 1;
invalid configuration or metadata exits 2. Experiment validation never runs a benchmark.

## Configuration

Precedence: environment variables > current-directory `.env` > explicit YAML/constructor values >
defaults. Prefix: `ARCHGUARD_`. See `.env.example` and `configs/app.example.yaml`.
Unknown fields fail. Provider credentials are read only from `OPENAI_API_KEY` and
`ANTHROPIC_API_KEY`; never put them in configuration or CLI arguments. Provider/model names are
optional metadata. Application directories can be absolute;
artifact and experiment output references must be relative POSIX paths without parent traversal.
Lexical path validation does not provide symlink containment or an execution sandbox.

## Quality and Docker

Provider configuration is offline-validatable. Doctor never makes a paid request:

```bash
OPENAI_MODEL=your-allowed-model ANTHROPIC_MODEL=your-allowed-model \
  uv run archguard provider config validate --config configs/providers.example.yaml
uv run archguard provider doctor --provider openai --config providers.yaml
```

API access is separate from consumer subscriptions, model access varies by account, and usage may
incur costs. Live smoke tests are opt-in. Structured output guarantees structure, not correctness;
Phase 5 architecture and Phase 7 sandboxed execution remain mandatory gates. See
[provider integration](docs/providers/overview.md).

Validate or inspect an immutable Phase 10 task without provider or repository execution:

```bash
uv run archguard repair task validate --task examples/repair/task.yaml
uv run archguard repair task inspect --task examples/repair/task.yaml
uv run python scripts/iterative_repair_demo.py \
  --task examples/repair/task.yaml --output /tmp/archguard-phase10-demo
```

Candidates and issue text are untrusted. Model assertions are never validation evidence; selection
uses only recorded applicability, architecture, sandbox execution, test-preservation and cleanup
evidence. Selected tests do not prove complete correctness, and Phase 10 performs no deployment.

Validate Phase 11 fixture metadata and run offline shape checks:

```bash
uv run archguard benchmark registry validate --registry configs/benchmarks.fixture.yaml
uv run archguard benchmark registry inspect --registry configs/benchmarks.fixture.yaml
uv run python scripts/benchmark_fixture_demo.py --fixture synthetic --output /tmp/benchmark.json
```

Acquisition is always explicit and outside tracked paths. Ordinary imports, tests and CI make no
benchmark network request. See [benchmark CLI](docs/benchmark-cli.md), [strategy](docs/research/benchmark-strategy.md)
and [gold quarantine](docs/research/gold-patch-quarantine.md).

```bash
make install
make check
uv build
uv run pre-commit install
uv run pre-commit run --all-files
docker compose config
docker build -t archguard-apr:phase-7 .
docker build -f Dockerfile.validation -t archguard-validation:phase-7 .
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
4. Completed: explicit architecture constraints and deterministic conformance.
5. Completed: isolated patch and architecture-delta validation.
6. Completed: deterministic graph context retrieval.
7. Completed: Docker-only execution feedback and functional validation.
8. Completed: provider-neutral multi-agent orchestration and deterministic replay.
9. Completed: secure API provider adapters.
10. Completed: iterative candidate/refinement control and deterministic evidence selection.
11. Current: reproducible benchmark metadata, dataset policy, and gold-patch quarantine. External
    acquisition and final scientific experiments remain future work.
12. Current: controlled baselines, ablations, deterministic offline pilots and a prospective Phase 13
    protocol. External/live pilots require explicit authorization and final evaluation remains untouched.

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

## Isolated patch validation

Phase 5 accepts a narrow textual Git unified-diff subset. It fingerprints the exact input bytes,
rejects unsafe paths and unsupported constructs before application, binds one full baseline commit,
and applies only inside a temporary detached worktree. The original repository must be clean and its
HEAD, branch, index, tracked status, and untracked status are proven unchanged afterward.

```console
archguard patch inspect candidate.diff
archguard patch validate repository --patch candidate.diff --profile architecture.yaml \
  --baseline 0123456789abcdef0123456789abcdef01234567 --source-root src \
  --output validation.json
archguard patch result inspect validation.json
archguard patch result delta validation.json
archguard patch result violations validation.json --state introduced
```

Exit codes are 0 (complete/pass), 1 (complete/gate failed), 2 (invalid input/artifact), 3
(rejected patch), 4 (incomplete comparison), and 5 (worktree/application failure). No patched code,
hooks, submodules, tests, or arbitrary commands are executed. Static architecture conformance and
resolved violations do not establish functional correctness. See the
[Phase 5 design](docs/architecture/patch-validation.md) and
[verification report](docs/phase-5-verification.md).

## Deterministic context retrieval

```console
archguard context query compile --problem examples/context/problem.txt --output query.json
archguard context retrieve graph.json --snapshot snapshot.json --query query.json --output manifest.json
archguard context inspect manifest.json
archguard context explain manifest.json file:src/demo/service.py
archguard context bundle repository repository --snapshot snapshot.json --manifest manifest.json --output context-bundle.json --include-source
archguard context bundle inspect context-bundle.json
archguard context evaluate manifest.json --labels examples/context/relevance-labels.yaml --output retrieval-evaluation.json
archguard context evaluation inspect retrieval-evaluation.json
```

Query, manifest and evaluation outputs are source-free. Bundles are explicitly
`sensitive-source-bearing`; creation requires `--include-source`, and normal inspection never
prints source. Exit codes are 0 complete, 1 no candidates, 2 invalid input/artifact, 3 source
acknowledgement refusal, 4 partial result, and 6 source identity mismatch. See the
[design](docs/architecture/context-retrieval.md), [schemas](docs/schemas/context-retrieval-v1.md),
and [Phase 6 verification](docs/phase-6-verification.md). Phase 7 evidence is in
[Phase 7 verification](docs/phase-7-verification.md).
