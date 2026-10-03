# Phase 12.8B verification

Status: implementation complete; external execution not run locally; `phase_13_ready=false`.

Baseline was clean local `main` at `336ff66454f86a3c8918873c79ad4b9f795db2e0`, version `0.12.8`.
The version remains `0.12.8`: this is a research-readiness subphase and does not change the package
release line. No human profile or protocol decision file is modified.

The manual workflow acquires only the pinned PySnooper buggy/fixed revisions, pinned BugsInPy metadata,
and pinned SWE-bench framework revision from official GitHub repositories. It announces the host,
repositories, 250 MiB ceiling, destinations, and credential requirement before acquisition. All
acquired content stays below `${RUNNER_TEMP}` and is removed before the single source-free ZIP is
uploaded. Target Python and repository commands are never imported or executed.

The graph pipeline analyzes only the buggy revision and runs twice in independent directories. The
evidence binds the graph to the task, revision, analyzer/schema, draft profile, and acquisition
manifest. The draft profile remains `REVIEW_REQUIRED`; a fingerprint change stops with
`PROFILE_REVIEW_INVALIDATED`.

License audit records are separate for PySnooper, BugsInPy, SWE-bench framework, and SWE-bench Verified.
Only immutable official license text with a recorded hash and defensible identifier can become
`VERIFIED`. Missing or ambiguous evidence remains `UNRESOLVED` without failing valid engineering
execution. This is not legal advice.

Run after merge from GitHub Actions → **Phase 12.8B License and Graph Evidence** → **Run workflow**.
Download `archguard-phase-12-8b-license-graph-<run-id>` and validate it with the commands in the schema
document. Import only after validation; do not commit the ZIP or acquired repositories.

Before external evidence import, blockers remain `INSUFFICIENT_QUALIFIED_TASKS`,
`INSUFFICIENT_PROJECT_DIVERSITY`, `INSUFFICIENT_CANDIDATE_POOL`, `PILOT_SELECTION_NOT_READY`,
`GRAPH_EVIDENCE_EXTERNAL_EXECUTION_REQUIRED`, `TASK_LIST_NOT_FROZEN`, `LICENSES_UNVERIFIED`,
`ARCHITECTURE_ANALYSIS_INCOMPLETE`, `PROFILE_REVIEW_REQUIRED`, `PROTOCOL_REVIEW_REQUIRED`, and
`PROVIDER_NOT_CONFIGURED`. Valid graph evidence may resolve only its supported graph/architecture
facts; it cannot approve reviews, freeze tasks, configure a provider, or make Phase 13 ready.

Local verification on 2026-10-04:

- Python 3.12.13: 669 passed, 3 skipped, 4 warnings; combined statement/branch coverage 90.20%.
- Python 3.13.13: 669 passed, 3 skipped, 4 warnings.
- Focused Phase 12.8/12.8A/12.8B and CLI tests: 68 passed, 2 expected duplicate-archive warnings.
- Ruff format/lint, strict mypy, frozen lock validation, pre-commit, workflow YAML parsing, version,
  doctor, offline-capable package inputs, sdist/wheel build, and self-architecture validation passed.
- `actionlint` and `shellcheck` were unavailable; workflow structure and embedded shell invariants were
  reviewed and covered by regression tests.
- Secret-pattern scan found only the deliberate scanner/test signatures. No benchmark repository,
  benchmark payload, provider API, Docker evaluator, Phase 13 experiment, or scientific artifact was
  acquired or executed locally.

PyPI access was used only for locked Python 3.13 test dependencies and the declared Hatchling build
backend. The displayed large-wheel transfers totalled 31.9 MiB; the isolated cache occupied 138 MiB,
the Python 3.13 environment 146 MiB, build cache 1.9 MiB, and built distributions 0.6 MiB. Phase 12.8B
scientific acquisition transfer and disk consumption are both zero locally; real acquisition metrics,
license conclusions, and graph fingerprints remain pending the manual workflow.
