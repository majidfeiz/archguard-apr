# V2.1A verification

- Baseline: `25d9a19cb61d1517d1b1cef5713af74228ac2244`
- Branch: `phase/v2-01a-micro-pilot-readiness`
- Final SHA: the single commit containing this report
- Provider calls: 0
- Scientific executions: 0
- New Linux/external qualification executions: 0

Official pricing was retrieved on 2026-11-04 from the specified OpenAI model and pricing pages and
matched the frozen proposal. Canonical pricing, call-plan, fairness, task-manifest, and readiness
artifacts include self-excluding SHA-256 fingerprints and one trailing LF.

The fresh internal security review found no unresolved critical or high code finding. The executable
cost guard and condition-fairness validator were added and mutation-tested. Historical Phase 13
evidence remains byte-unchanged.

Verification completed on Python 3.12.13: 1,028 tests passed, one was skipped, and three Docker
tests were deselected; combined statement and branch coverage was 90.16%. Focused V2.1/V2.1A
tests, cost boundaries, manifest contradictions, fairness mutations, leakage checks, patch
regressions, architecture rules, Ruff format/lint, strict mypy, canonical byte regeneration,
workflow parsing, package build, and `git diff --check` passed. The Python 3.13 interpreter was
present, but the locked Python 3.13 mypy wheel was not cached, so the optional offline 3.13 suite
was not run. The package sdist and wheel built from cached dependencies.

Provider-free preflight produced source-free immutable reports: PySnooper-2 was `BLOCKED` with
`CHECKOUT_IDENTITY_MISMATCH`; PySnooper-3 was `READY`. Neither preflight accessed task source,
executed a candidate, or contacted a provider.

Final verification results and exact changed-file inventory are recorded in the completion handoff.
Readiness is `V2_MICRO_PILOT_BLOCKED` because the PySnooper-2 historical evidence does not retain the
fixed checkout Git-tree identity and this phase was prohibited from reacquiring the external
repository.
