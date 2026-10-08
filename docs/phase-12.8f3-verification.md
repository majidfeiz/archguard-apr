# Phase 12.8F.3 execution-path verification

Baseline `d84028318ec94b5ed9d3cec95c864276e3699271`, version `0.12.8`, was clean before
the F.3 branch was created. Run `37684840237` is diagnostic evidence only: its outer SHA-256 is
`2b4f61190db4735e301b54a99b6c93b2cb5eb8c20eb149f8a462ecdfde22b391`. It qualified zero tasks and
is not imported.

The audit proved an expectation-normalization defect: the old execution function mapped every
nonzero exit to `EXPECTED_FAILURE`, including fixed controls whose declared success condition was
`EXIT_ZERO`. The dependency image did not contain target source. The runner mounted the supplied
checkout at runtime, so the three equal buggy/fixed signatures do not prove buggy-source reuse.

F.3 makes the expectation explicit per invocation, uses a dependency-only immutable image, mounts
each independently verified checkout read-only at `/workspace`, and verifies a deterministic
container-visible tree fingerprint before executing there. Evidence binds requested revision,
resolved revision, HEAD, Git tree, build context, host working tree and container-visible tree.
Mismatch fails closed. Fixed controls can never be normalized as `EXPECTED_FAILURE`.

The workflow is `Phase 12.8F.3 Batch A Execution-Path Verification`. It accepts only Batch A and
produces one source-free artifact named
`archguard-phase-12-8f-qualification-batch-a-<run-id>`. It does not import that artifact. Batch B and
Phase 13 remain prohibited; `phase_13_ready=false`.

Run `37746821705` exposed a packaging-only invariant error: failed fixed selectors correctly recorded
zero collected tests, but validation required every attempted control to collect at least one. The
validator now requires positive collection only for passing controls and accepts truthful zero-count
selector/import/collection failures without weakening qualification.
