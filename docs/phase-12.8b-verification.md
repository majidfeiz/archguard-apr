# Phase 12.8B verification

Status: validated evidence imported; profile human review required; `phase_13_ready=false`.

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

- Python 3.12.13 after import: 673 passed, 3 skipped, 4 warnings; combined statement/branch
  coverage 90.31%.
- Python 3.13.13 after import: 673 passed, 3 skipped, 4 warnings.
- Focused Phase 12.8/12.8A/12.8B and CLI tests after import: 72 passed, 2 expected
  duplicate-archive warnings.
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
scientific acquisition transfer and disk consumption were both zero during local implementation. The
later workflow evidence records 9,803,386 acquired bytes; its conclusions and fingerprints follow.

## Validated evidence import

GitHub Actions run `37152285061` produced the inner source-free archive with SHA-256
`5a793348ba02ef002ee1cadd826d2dcc049089d4da928bbf41e1eeb6b90c8cef`. The unchanged validator
accepted the exact nine-member allowlist, checksums, canonical JSON, identity bindings, security scan,
and cleanup record. The original archive directory was read-only in the local sandbox, so the already
hash-verified bytes were copied to `/tmp` and re-hashed before validation.

Imported identities:

- Manifest: `f8717760da78312db0023d0fb22ed3b6ee689a4ecac5a2f30b3902a70983aaab`
- Import: `6277810062743dfd274fc0e03a51a0d6f29b79ba6da45ab9fbabff99b0197648`
- Imported file SHA-256: `8a1193c6940f88681f756e0aacc3dc3c31399861e5a2e2b98ad31a19e944ee6d`
- Graph evidence: `e08af7f18e793a17e06721127ebf43d791c299a92702dba5c06d932ab527ab1e`
- Canonical graph: `b1c318faba70d50225ceba74254edb18727013291de8607695334f8f0a98802c`
- Acquisition: `b5820205e5339b0a64a7efdfef6bd74cb71b90d58a18f90fa9847af4123f4c1f`
- Profile: `e2694d6a8016382036a3670476d75a0ca16d7f9872678156d16fba6de0f441f1`

Three independent imports were byte-identical. Re-importing identical evidence is idempotent;
contradictory overwrite is rejected. The graph has 14 modules, 12 assigned, 2 unassigned (`setup` and
`misc.generate_authors`), 0 ambiguous, 19 internal edges, 43 external edges, 14 SCCs, and 0 cycles.
Four of five rules evaluated with zero violations. `production-components-acyclic` was skipped for
`incomplete_assignments`; consequently `partial=true`, `passed=false`, and architecture analysis is
not complete.

PySnooper and the SWE-bench framework are verified MIT. BugsInPy and SWE-bench Verified remain
unresolved, and benchmark redistribution remains unresolved. Only
`GRAPH_EVIDENCE_EXTERNAL_EXECUTION_REQUIRED` is resolved. All insufficient-count/diversity/pool,
pilot-selection, task-freeze, license, architecture-completeness, profile-review, protocol-review, and
provider blockers remain. `phase_13_ready=false`.
