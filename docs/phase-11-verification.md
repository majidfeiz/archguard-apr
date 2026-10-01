# Phase 11 verification

Date: 2026-10-01 (Asia/Tehran). Baseline SHA:
`be753459cc1e0296fb5d008d191dbaee8b77a580` on clean `main`, version `0.10.0`.
Baseline verification found Phase 6–10 components and passed 535 tests with 3 Docker skips and two
dependency deprecation warnings. Work continued on `phase/11-benchmark-pipeline`.

## Recorded results

- Python 3.12: 567 passed, 3 Docker tests skipped, 2 dependency warnings; Docker slice separately
  passed 3/3 against validation image
  `sha256:e4aea41738c84d8467103043606d66e62e453429331a9922e2b9aca7672d5979`.
- Python 3.13.13: 567 passed, 3 Docker tests skipped, 2 dependency warnings.
- Phase 11 focused: 32 passed. Phase 5–10 regression selection: 125 passed.
- Coverage: 5988/6449 statements (92.85%), 1090/1312 branches (83.08%), combined 91.20%.
- Ruff format/lint, strict mypy, lock check, and all-file pre-commit passed.
- Package build produced 0.11.0 sdist/wheel; CLI reported 0.11.0 and doctor passed.
- Registry fixture validated offline with fingerprint
  `31186a7f55942a002bbf6300d8c1e847b4bd9c1e3574b5912b1ee674ba364f3e`.
- Synthetic output was byte-identical across two runs, SHA-256
  `61229ec5c69529b830981eb0c4eb962a9ca8deb10205d642acfb0f4d47255afd`.
- BugsInPy-compatible fixture SHA-256:
  `b003597c20ae039d1a47d3dbc1963138c3d52c9fbf1fa9d41f5e70bad364eac6`.
- SWE-bench-compatible fixture SHA-256:
  `e2dc0f2d07452ad67d625043515b05037608aaaa0cb3326c4f3e74f90716a59a`.
- Eligibility, explicit exclusions, split grouping/sampling, cache corruption, snapshot identity,
  license metadata, prohibited fields, and prompt/log/feedback/output canaries passed focused tests.
- Self-architecture: 150/150 modules assigned, 7 rules evaluated, zero violations, passed.
- Compose configuration passed. `archguard-apr:phase-11` built as
  `sha256:14ec6e3959720c9f992b447ee89a5e541e72470659207a7e7e48666ccc221b8a`.
- Integrity checks found one expected worktree, no orphan `archguard-*` containers, no committed
  benchmark cache/output, and no private key or credential value. `.env.example` contains documented
  runtime placeholders only. Gold canaries occur only in scanner implementation/tests; no gold patch,
  hidden test, fixed source, dataset, or external repository is committed.

## Scope and limitations

No external BugsInPy or SWE-bench task was downloaded, acquired, built, reproduced, made eligible, or
evaluated. Actual external eligibility counts are therefore zero observed, not zero failures.
The fixtures establish local schema/policy behavior only; they do not establish external benchmark
compatibility. Acquisition adapters and real evaluator adapters remain future work. No pilot or final
scientific experiment ran, and no research question was answered. License conclusions for external
benchmarks/projects remain unresolved until official metadata is inspected during explicit acquisition.
Mac ARM fixture checks are not final Linux/x86_64 results. GitHub Actions was not run because this
branch was not pushed; the ordinary and manual workflows were validated locally as YAML/pre-commit
inputs only.
