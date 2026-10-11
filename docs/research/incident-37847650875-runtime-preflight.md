# Incident timeline: run 37847650875

- Run `37847650875` completed source-free artifact production at baseline `44d9d39`.
- PySnooper-1, PySnooper-3 and black-1 stopped at `PROJECT_IMPORT_FAILED`.
- Cookiecutter-4 stopped at `TOX_CONFIGURATION_INVALID`.
- No evaluator mount, evaluator identity, import, collection, buggy scientific attempt, or fixed
  control was proven by runtime transition evidence.
- The run produced zero scientific executions and zero qualifications and remains non-imported.
- The common Python import cause is unresolved because the source-free artifact retained only the
  normalized runner category, not the underlying stderr, and local Docker was unavailable.
- Phase 12.8F.4.2 narrows execution to PySnooper-1 and adds exact source-free transition diagnostics.

## Follow-up run 37850406131

The PySnooper-1 canary proved fixture acquisition, fixture identity, and installation preparation,
then stopped at `MOUNT_PROBE_TEMPORARY_WRITABLE`. The dedicated `/tmp/archguard` tmpfs replaced the
image-owned directory without explicit runtime UID/GID/mode and rejected the non-root write probe.
No scientific attempt ran and the fixed control was not attempted. Phase 12.8F.4.2.1 uses one explicit
`/tmp` tmpfs and creates its child directories as the mounted runtime user.

## Follow-up run 37896070272

The PySnooper-1 canary proved the repaired tmpfs topology, source and evaluator mounts, evaluator
identity, and target-project import. It then stopped at `EVALUATOR_IMPORT_FAILED` before collection,
with zero buggy scientific attempts and no fixed execution. The preflight incorrectly executed the
standalone pytest fixture with generic `runpy.run_path()` semantics. Phase 12.8F.4.2.2 instead treats
successful exact-node pytest collection as the evaluator-loading proof.

## Follow-up run 38035903312

The PySnooper-1 canary again reached `PROJECT_IMPORT_VERIFIED`, then stopped with
`EVALUATOR_SELECTOR_NOT_FOUND` before evaluator-load verification or collection. The source-free
artifact proves the intended runtime-selector fingerprint, mounted fixture identity, zero collection,
and zero scientific attempts, but deliberately retains no raw pytest output. Phase 12.8F.4.2.3 binds
logical, physical, and runtime selector identities explicitly, rechecks the physical fixture before
collection, and retains bounded source-free collection diagnostics.
