# Phase 12 verification

Date: 2026-10-01 (Asia/Tehran). Baseline SHA:
`61ff04861178248a68b2016d06051cdd2d7b1971`, clean `main`, version `0.11.0`.
Phase 11 registry/split/eligibility/quarantine, Phase 10 repair, and Phase 9 providers were present.
Baseline: 567 passed, 3 Docker tests skipped, two dependency warnings, 91.20% combined coverage.

## Phase 12 evidence

- Python 3.12: 580 passed, 3 Docker tests skipped, two dependency warnings.
- Python 3.13.13: 580 passed, 3 Docker tests skipped, two dependency warnings.
- Focused experiment framework: 13 passed. Phase 5–11 regression selection: 151 passed.
- Coverage: 6490/6974 statements (93.06%), 1155/1386 branches (83.33%), combined 91.45%.
- Ruff format/lint, strict mypy, frozen lock, all-file pre-commit and package build passed.
- CLI version 0.12.0 and doctor passed. Compose configuration passed.
- C0–C6 exist; C2–C6 fairness checks each permit exactly one conceptual difference from C1.
- Randomized block schedule: 4 tasks × 7 configurations × 2 repetitions = 56 unique runs.
- Evaluation and excluded splits are rejected before Phase 12 access; DEVELOPMENT/PILOT pass.
- Lexical baseline, metrics, descriptive distribution, paired differences, missingness, blinded labels,
  ledger integrity, immutable CSV, status and provider-disabled replay/resume passed.
- Offline artifacts were byte-identical across two executions. SHA-256:
  - blind mapping: `69daee76f028acfa86331956e87ef79be5099804a1e4bd0cc42ec92bdaa756d4`
  - comparison: `a709283e26267e41fdebd7e710d649f584e8d7c6865a341955554978374c2656`
  - ledger: `c99b22598a461e6561418b015abdeacf154caa42ed3e6d88aa5bd9fce667fb9b`
  - CSV: `77d44825f70be5b55718fc2d0ca80f8d6564a4252db26f9a3f6719f0507915dc`
  - schedule: `b1db4c8282087bae057aeb5a9557f069449a0488cc334ad53791771353151b65`
  - summary: `5eaec2eb9f96478a2f2ce15f4e2512aaaedaa91ab8366667fe1e6a9b69e7d9e6`
- Ledger fingerprint: `a8923debd92f92b403e3f64f0141cacaad47ab89cc24547686a527df954ea142`.
- Experiment-plan fingerprint: `00bec055da32bc881eed5343a077b20227d44dfd8a636e5291532ec9ec4ec5fe`.
- Self-architecture: 157 modules assigned, 7 rules, zero violations, passed.
- Docker sandbox: 3 passed using digest-pinned Phase 7 validation image. Phase 12 application image
  built as `sha256:5b519878695e5b22be78b5b42dda8b107210becfb2bc99377f09f858a6df1178`.
- Secret scan found only documented `.env.example` placeholders. Gold canaries occur only in the
  Phase 11 scanner and tests. One expected worktree and no orphan ArchGuard containers were present.

## Scope and readiness

The offline fixture contains scripted known outcomes only. It is not provider or benchmark evidence,
and its descriptive numbers are not scientific results. The external infrastructure pilot was not
executed. Live LLM pilot not executed — explicit cost and benchmark authorization not provided.
No `EVALUATION` task was accessed. GitHub Actions was not run because the branch was not pushed.

The prospective Phase 13 analysis plan and engineering gates are frozen in documentation, but Phase 13
is not operationally ready until official external task acquisition/licensing, evaluator stability,
eligible frozen evaluation tasks/profiles, dated price information and authorized pilot gates pass.
