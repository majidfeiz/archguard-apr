# Phase 12.8E verification

Baseline: clean local `main` at `ed74b515a54ef3b1ee6f000506c3a650d164b41d`, version `0.12.8`.
Phase 12.8D, imported Linux x86 evidence, and approved/frozen PySnooper profile fingerprint
`950cd9889d5d4335e60b7429d2feddf2230db42654e5ec844edd813596b6d6d7` were verified before work.
The profile, its approval/history, and the pending confirmatory protocol decision were not changed.

Official GitHub repositories for BugsInPy, PySnooper, Black, and Cookiecutter were inspected only at
immutable revisions. No credentials were used. Git did not expose wire-byte counters; the measured
post-fetch Git-object footprint was 9,535,488 bytes and maximum simultaneous external disk was
21,041,152 bytes. Hooks, submodules, and LFS smudging
were disabled. No acquired code or evaluator ran. Temporary repositories were removed after audit.
SWE-bench conclusions reuse the imported immutable evidence; no Verified payload was downloaded.

The audit verifies PySnooper/Black as MIT, Cookiecutter as BSD-3-Clause, and the SWE-bench framework as
MIT. BugsInPy and SWE-bench Verified remain unresolved. Eleven scoped records were observed; eight are
eligible and selected across three projects, while three are excluded for unsupported gitlinks. See
the canonical registries for fingerprints and identifiers. The preparation pool resolves
`INSUFFICIENT_CANDIDATE_POOL` and preparation-level diversity only. Qualification, final selection,
task freeze, dependency licensing, protocol review, and provider configuration remain blocked.
`phase_13_ready=false`.

Run the manual GitHub Action **Phase 12.8E License Candidate Preflight** with `workflow_dispatch`. It
regenerates records twice, compares tracked bytes, scans for license/gold/source/secret violations,
verifies cleanup, and uploads exactly one flat source-free artifact for 14 days. It performs no
external acquisition and no project/evaluator execution.
