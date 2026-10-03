# Phase 12.8 verification

Baseline `8db89df81afa72f8af87d751383304771c3d45ea` on macOS/Python 3.12.13: 601 passed,
3 skipped, 2 warnings, 91.50% combined statement/branch coverage. Frozen dependency synchronization was
blocked by unavailable network/cache; the existing locked environment was used for the baseline.

The evidence-import continuation started from merged Phase 12.8 commit
`3084fbd5c4a978a1443494f6e47dfb3b90f7a9cc`; it includes the legitimate pending-report CI fix
`88b79c05e61edac1c4f771580f0a109ffd22fbce`.

The Phase 12.7 artifact from GitHub Actions run `37009930401`, job `110846968717`, was validated with
SHA-256 `8d3d261e368a1c6bd585f33065cdcda39e4a1924f52ef9763a144d9559f8a498`. The original validator
incorrectly sent full 40-character Git SHA-1 commit object IDs to a raw SHA-256 validator. The fix
separates exact lowercase Git SHA-1 commit IDs, unprefixed SHA-256 values, and `sha256:`-prefixed Docker
image IDs. Regression tests cover length, case, alphabet, whitespace, cross-type substitution, and the
existing archive-security boundaries. Validate/import with:

```console
archguard readiness evidence validate --archive /absolute/path/to/artifact.zip
archguard readiness evidence import --archive /absolute/path/to/artifact.zip --output research/evidence/phase-12.7-x86.json
```

The importer enforces a byte limit and exact file allowlist and rejects hash mismatch, traversal,
absolute/non-flat names, duplicate names, symlinks/devices/directories, oversized or high-ratio members,
binary/non-UTF-8 content, missing fields, inconsistent revisions, nonmatching runs, failed fixed control,
wrong platform, incomplete quarantine/cleanup, and a failed conclusion.

The canonical imported manifest is `research/evidence/phase-12.7-x86.json`. Three independent temporary
imports and the tracked import were byte-identical. Manifest SHA-256:
`b57e8a8fdf3eb09aeefd0a761248d361ab00c884e823239a6a2d45370f6b1b40`; domain fingerprint:
`a3a361aecb2c6c3eb3a1bcf570e148da1c98e49f1260f0f96fdf9f6e9f51ccf9`.

The imported pilot resolves `PHASE_12_7_EVIDENCE_MISSING`, `EVALUATORS_UNQUALIFIED`, and
`LINUX_X86_EVIDENCE_MISSING` for one PySnooper-2 evaluator on Linux x86_64. Candidate selection still
contains zero Phase 12.8 candidates: BugsInPy framework licensing remains unresolved,
and SWE-bench payload acquisition is prohibited in this phase. This is not a negative benchmark result.
`INSUFFICIENT_QUALIFIED_TASKS`, `INSUFFICIENT_PROJECT_DIVERSITY`, `TASK_LIST_NOT_FROZEN`,
`LICENSES_UNVERIFIED`, `ARCHITECTURE_ANALYSIS_INCOMPLETE`, `PROFILE_REVIEW_REQUIRED`,
`PROTOCOL_REVIEW_REQUIRED`, and `PROVIDER_NOT_CONFIGURED` remain. The PySnooper draft profile and
protocol decisions are pending. Therefore `phase_13_ready=false`.

Post-import local verification on Python 3.12.13: focused Phase 12.8 tests 40 passed with one expected
duplicate-ZIP construction warning; full suite 641 passed, 3 skipped, 3 warnings, and 91.31% combined
statement/branch coverage. Ruff format/lint, strict mypy (154 source files), frozen lock/sync, package
sdist/wheel build, version, doctor, source/gold/secret scans, canonical JSON checks, and repository diff
checks passed. Self-architecture evaluated 172 modules and seven enabled rules with zero violations.
`actionlint`, `shellcheck`, and Python 3.13 were unavailable locally and were not claimed.

The repository follows its established major-tag Actions policy (`actions/checkout@v6`,
`actions/upload-artifact@v4`, `astral-sh/setup-uv@v6`); these are not immutable commit pins, which is a
supply-chain limitation. Workflows do not claim local GitHub Actions execution.

The Phase 13 workflow treats pull requests as report-validation runs: a valid fail-closed report with
blockers is uploaded and does not make an otherwise healthy Phase 12.8 pull request fail. Manual
dispatch is the enforcing gate and exits nonzero whenever `phase_13_ready` is false. Unexpected CLI or
schema failures remain errors in both modes.
