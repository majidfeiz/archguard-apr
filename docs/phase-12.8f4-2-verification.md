# Phase 12.8F.4.2 evaluator runtime canary

Baseline: `44d9d398d63e2d67e8dedcb9f6fdb980012828d0`, version `0.12.8`.

Run `37847650875` produced zero scientific executions and zero qualifications. Its source-free
artifact is historical and non-imported. The retained evidence proves that project-import preflight
was the common recorded stopping point for PySnooper-1, PySnooper-3 and black-1, but it does not retain
the underlying stderr. Docker is unavailable in the local verification environment, so a shared root
cause cannot be proven and remains unresolved.

The Phase 12.8F.4.2 manual workflow runs only PySnooper-1. It records actual, ordered runtime
transitions rather than treating reviewed adapter metadata as runtime proof. Target source is mounted
read-only at `/workspace`, the byte-bound evaluator is mounted read-only at `/evaluator`, dependencies
are exposed at `/wheelhouse`, and writable data is limited to `/tmp/archguard` and `/tmp/home`.
`PYTHONPATH=/workspace`, the working directory is `/workspace`, and the only allowlisted project module
for this canary is `pysnooper`.

PySnooper-3 is deferred until the shared PySnooper canary runtime passes. Black-1 is deferred until the
mount/import state machine passes. Cookiecutter-4 is deferred to a later offline-tox-specific canary.
Batch B and Phase 13 remain prohibited, and `phase_13_ready=false`.

Expected artifact name:
`archguard-phase-12-8f4-2-pysnooper-1-runtime-canary-<run-id>`.
