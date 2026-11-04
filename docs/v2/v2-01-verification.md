# V2.1 verification

## Baseline and environment

- Branch: `phase/v2-01-patch-reliability`
- Baseline SHA: `7e8a5797a5b03590ced7c01552f205f828531418`
- Final SHA: the single commit containing this report (reported in the completion handoff)
- Package version: `0.12.8` (unchanged)
- Baseline Python: 3.12.13
- Baseline suite: 994 collected; 990 passed, 4 skipped; 90.01% combined statement/branch coverage

## Exact changed-file inventory

Modified: `README.md`, `src/archguard/entrypoints/cli/experiment.py`.

Added: `.github/ISSUE_TEMPLATE/architecture_profile_proposal.yml`,
`.github/ISSUE_TEMPLATE/benchmark_adapter_proposal.yml`,
`.github/ISSUE_TEMPLATE/reproducibility_failure.yml`,
`docs/architecture/decisions/ADR-0029-v2-patch-reliability-boundary.md`,
`docs/schemas/v2-patch-diagnostics.md`, `docs/schemas/v2-repair-response.md`,
`docs/v2/README.md`, `docs/v2/experiment-design.md`,
`docs/v2/invalid-patch-root-cause-audit.md`, `docs/v2/patch-reliability.md`,
`docs/v2/roadmap.md`, `docs/v2/v2-01-verification.md`,
`examples/v2/preflight-ready.json`,
`research/v2/cost/proposed-micro-pilot-cost-plan.json`,
`research/v2/protocol/proposed-ablation-protocol.json`,
`research/v2/readiness/v2-01-readiness.json`,
`src/archguard/application/ports/v2_patch.py`,
`src/archguard/application/services/v2_patch.py`, `src/archguard/domain/v2_patch.py`,
`src/archguard/domain/v2_preflight.py`,
`src/archguard/infrastructure/v2_patch_response.py`,
`src/archguard/infrastructure/v2_preflight.py`, `tests/fixtures/v2_patch/README.md`,
`tests/fixtures/v2_patch/absolute-path.diff`,
`tests/fixtures/v2_patch/architecture-rejection.diff`,
`tests/fixtures/v2_patch/binary.diff`, `tests/fixtures/v2_patch/context-mismatch.diff`,
`tests/fixtures/v2_patch/empty-response.json`, `tests/fixtures/v2_patch/malformed.diff`,
`tests/fixtures/v2_patch/multiple.txt`, `tests/fixtures/v2_patch/no-op.diff`,
`tests/fixtures/v2_patch/path-traversal.diff`,
`tests/fixtures/v2_patch/policy-rejection.diff`,
`tests/fixtures/v2_patch/prose-only.txt`, `tests/fixtures/v2_patch/rename.diff`,
`tests/fixtures/v2_patch/symlink.diff`, `tests/fixtures/v2_patch/truncated.diff`,
`tests/fixtures/v2_patch/valid-fenced.txt`,
`tests/fixtures/v2_patch/valid-structured.json`, `tests/fixtures/v2_patch/valid.diff`,
`tests/unit/test_v2_artifacts.py`, `tests/unit/test_v2_patch_response.py`, and
`tests/unit/test_v2_preflight.py`.

## Verification results

- Focused V2 tests: 29 passed.
- Patch/security/architecture selection: 94 passed after the fixture assertion correction.
- Python 3.12 full suite: 1,023 collected; 1,019 passed, 4 Docker/platform skips;
  90.13% combined statement/branch coverage.
- Python 3.13.13 offline full suite: 1,023 collected; 1,019 passed, 4 skips.
- Ruff format check and Ruff lint: passed.
- Strict mypy over `src` and `tests`: passed (206 source files at the time of the check).
- Publication regeneration/validation: byte-stable; 49 bilingual section pairs and 23 verified
  references passed.
- V2 preflight regeneration: byte-identical canonical JSON across independent generation.
- Offline package build: source distribution and wheel built for version 0.12.8.
- Docker: `docker compose config --quiet` passed; no workload was started.

Security scans found no V2 secret, absolute local path, temporary-worktree path, symlink, benchmark
source, provider output, third-party source, or gold patch leakage. The only credential-like scan
matches were the pre-existing runtime placeholders in `.env.example`. Parsing tests guard `eval`,
`exec`, and dynamic import; Phase 5 tests confirm isolated application, primary-checkout immutability,
and cleanup after success/failure.

## Historical integrity and readiness

Git byte comparison against the baseline confirms no change under `research/results/phase-13`, the
two Phase 13 checkpoint evidence files, frozen provider configuration, or provider configuration
history. No provider/model call and no scientific repair run occurred.

V2.1 is not ready for a paid micro-pilot. Remaining blockers are independent security review,
qualified real-task manifests and preflight evidence, a dated model/pricing fingerprint, an exact
prospective maximum-call plan, and explicit micro-pilot approval. The proposed hard ceiling is USD
1.00 with no automatic continuation; provider calls remain disabled.
