# Phase 12.6 verification

Started: 2026-10-01; completed: 2026-10-02

## Baseline and scope

- Baseline branch: `main`
- Baseline SHA: `e0d79ced1c506f6dd7cb8d84fdcfb33094cc788b`
- Baseline version: 0.12.5
- Baseline suite: 598 passed, 3 skipped, 2 warnings
- Work branch: `phase/12.6-local-micro-pilot`
- Paid provider calls: 0

The initial host gate passed with 51 GiB free. Existing Docker use was 40.88 GB images, 183 MB
containers, 35.35 GB volumes and 20.70 GB build cache. Nothing pre-existing was deleted.

## Real qualification evidence

- Selected/acquired: PySnooper-1 and PySnooper-2; one shared buggy source archive.
- Reproduced: 1 of 2 (`PySnooper-2`, `STABLE`).
- Evaluator-qualified: 1 of 2.
- Architecture-analyzed: 1 of 2.
- Profile drafts: 1, status `REVIEW_REQUIRED`; human-reviewed/frozen: 0.
- Gold leakage: no gold identifier or patch content entered tracked files, agent-visible source,
  repository graphs, context manifests, or provider requests.
- SWE-bench metadata revision retained from Phase 12.5; execution `SKIPPED_RESOURCE_LIMIT`.

PySnooper-1 passed its declared evaluator test on the buggy revision in all three runs and therefore
is not reproducible. PySnooper-2 failed with the same declared defect three times and its trusted fixed
revision passed. See `docs/research/local-micro-pilot.md` for evaluator adaptations and limitations.

## Resource result

- Final free host space: 49 GiB (approximately 2 GiB below the initial rounded measurement).
- Final benchmark root: 13,164 KiB.
- Final Docker images: 41.10 GB, approximately 0.22 GB above the rounded initial value.
- Known exact/declared transfer: 68,528,386 bytes plus approximately 1,421 kB reported by pip and
  unmetered small registry metadata responses.
- Maximum concurrent real task: 1; provider calls: 0.

## Verification checklist

| Check | Result |
| --- | --- |
| Frozen sync and lock check | passed |
| Ruff format and lint | passed |
| Strict mypy | passed for 147 source files |
| Phase 12.6/readiness focused tests | 21 passed |
| Full suite | 601 passed, 3 skipped, 2 warnings |
| Combined statement/branch coverage | 91.50% |
| Pre-commit | passed |
| Package build | source distribution and wheel built |
| Version / doctor | 0.12.6 / passed |
| Docker Compose | valid |
| ARM64 / AMD64 smoke | `aarch64` / `x86_64` |
| Self-architecture | 165/165 modules assigned; zero violations |
| PySnooper graph determinism | byte-identical repeated artifacts |

Real evidence is not equated with final scientific evaluation. Phase 13 remains blocked by profile
review/freeze, protocol review/freeze, more representative task qualification, resolved SWE-bench
licensing/evaluation, and native Linux x86_64 execution.
