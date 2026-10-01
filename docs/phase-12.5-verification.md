# Phase 12.5 verification

Date: 2026-10-01

## Baseline

- Branch before work: `main`
- Baseline SHA: `008453afa4afcc6ba3c1d4319041f5818c9d9c93`
- Baseline version: `0.12.0`
- Baseline worktree: clean
- Baseline suite: 580 passed, 3 skipped, 2 warnings; 91.45% combined statement/branch coverage
- Implementation branch: `phase/12.5-external-benchmark-readiness`

The baseline matched the requested authoritative revision. No Phase 13 implementation branch or local
advance had to be reconciled.

## External evidence

All acquired material remained below `/tmp/archguard-phase125-external`, outside the Git worktree.
Clones disabled hooks and submodule initialization. No target code was imported or executed.

| Subject | Official source | Immutable revision | Observed result |
| --- | --- | --- | --- |
| BugsInPy framework | `https://github.com/soarsmu/BugsInPy` | `11c5f1eea954a42132cfd06bf257766a7963e0fd` | 17 project directories and 501 `bug.info` records; checkout quarantined because reference-patch files are present |
| SWE-bench harness | `https://github.com/SWE-bench/SWE-bench` | `02e7a74ffd0b707aab73d203fe87bdc7c76afc8e` | Framework metadata acquired; MIT license file verified |
| SWE-bench Verified metadata | `https://huggingface.co/datasets/SWE-bench/SWE-bench_Verified` | `78f471bf655a3137b2e8a75af1501690ec009ec3` | Official 500-task declaration verified without downloading dataset payload |

The source-free registry hash is
`04e16d604b35b16d777c76048bbb7b274ec63e6cf6fb6c40702f7ceb4eb691c2`. The
source-free preflight hash is
`46d4e4e88d9aa2daf9af730aa9dfa476b839438942a587e8174cfa0bc0c3abb9`.

License outcomes are intentionally conservative: the SWE-bench framework license is verified as MIT;
the BugsInPy framework license is unresolved because no license file was found at the inspected
revision; the SWE-bench Verified dataset license and every not-yet-selected upstream task-project
license are unresolved. No external source is approved for redistribution.

## Qualification counts

| Evidence class | Actual count or result |
| --- | --- |
| Real task repositories acquired | 0 |
| Reproduced real baselines | 0 |
| Stable / flaky / environment-sensitive / not reproducible | 0 / 0 / 0 / 0; all unattempted tasks remain unknown |
| Real evaluators qualified | 0 |
| Real architecture analyses | 0 |
| Project profile drafts | 0 |
| Profiles requiring review | 0 actual profiles; the profile gate itself requires human review |
| Human-reviewed / frozen profiles | 0 / 0 |
| Real infrastructure-pilot tasks | 0 |
| Paid provider or live-LLM calls | 0 |

These zeroes are results, not omitted work: task selection and execution would be premature while
license, resource, platform and human-review gates remain unresolved. Candidate replacement was not
used to manufacture a target count.

## Host and readiness

- Host: Darwin ARM64 (`arm64`), kernel `27.2.0`.
- Docker server: Linux `arm64`, Docker 29.8.0, 12 CPUs, 33,598,197,760 bytes of memory.
- Linux x86_64 final-execution evidence: absent.
- Live-pilot cost: unknown; no dated provider/model pricing or approved monetary ceiling exists.
- Hypotheses and endpoints: `PROPOSED`, human review required.
- Statistical decisions: `PROPOSED`, human review required.
- Readiness artifact: `archguard.external-readiness/v1`, 10 gates, fingerprint
  `a33fa5bdf954c8bf7d6b919d3e6aa23edb19af418861fd058ea115880812080e`.
- Overall Phase 13 status: `REVIEW_REQUIRED`; not pilot-ready and not final-evaluation-ready.

## Verification matrix

| Check | Result |
| --- | --- |
| Python 3.12 full suite with branch coverage | 598 passed, 3 skipped, 2 warnings; 91.46% |
| Python 3.13 full suite | 598 passed, 3 skipped, 2 warnings |
| Phase 12.5 focused tests | 18 passed |
| Ruff formatting and lint | passed |
| Strict mypy | passed for 145 source files |
| Pre-commit | passed |
| Frozen lock validation | passed |
| Package build | source distribution and wheel built successfully |
| Version / doctor | 0.12.5; doctor passed |
| Self-architecture | 163/163 modules assigned, 7 rules evaluated, zero violations |
| Docker Compose validation | passed |
| Application image | built as `archguard-apr:phase-12-5` |
| Docker fixture image | `sha256:18e6f4a7f364ec77f0c0a74490f1ac3550d0d3e01db71606bd0e5836b55cbdb0` |
| Docker fixture tests | 3 passed |
| Phase 5–12 regressions | covered by the full 598-test suite; passed |
| Gold scan | no benchmark gold/reference artifact tracked; deliberate field-name canaries exist only in policy code, tests and documentation |
| Secret scan | no private-key material or live provider-key pattern found outside tests |
| Primary repository integrity | single expected worktree; external benchmark material absent from tracked paths |
| Orphan check | no ArchGuard containers remained; unrelated pre-existing stopped containers were not modified |
| GitHub Actions | not run locally |

The complete verification suite demonstrates implementation integrity only. It does not substitute for
real-task reproduction, evaluator qualification, human review, protocol freeze or Linux x86_64 evidence.

## Remaining blockers

1. Resolve benchmark/dataset licensing and audit each selected upstream project.
2. Select and acquire real tasks with the frozen deterministic policy.
3. Reproduce baselines repeatedly and qualify official/adapted evaluators.
4. Run deterministic repository analysis and draft evidence-based profiles.
5. Obtain external human profile decisions and freeze only approved fingerprints.
6. Review and freeze hypotheses, endpoints, statistical decisions and dated cost ceilings.
7. Execute the infrastructure pilot and final protocol on a qualified Linux x86_64 host.

No live-LLM pilot or final evaluation was executed.
