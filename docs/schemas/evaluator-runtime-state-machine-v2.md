# Evaluator runtime state machine v2

Schema `archguard.evaluator-runtime-state-machine/v2` preserves v1 and inserts `TMPFS_CREATED` and
`WRITABLE_PATHS_VERIFIED` after `INSTALLATION_PREPARED` and before `SOURCE_MOUNTED`. This ensures no
source/evaluator mount claim precedes the mounted-container and writable-path checks.

The writable transition is based on behavior after the `/tmp` tmpfs exists. Four role-fingerprinted
directories must exist, must not be symlinks, must resolve outside protected mounts, must report tmpfs,
must be ownership-compatible with UID/GID `65532:65532`, and must pass create/write/fsync/stat/delete
with cleanup. `noexec` is required and no probe file is executed. Only fingerprints, booleans, the
allowlisted mount category, and transition fingerprints enter evidence.

Phase 12.8F.4.2.2 preserves this ordering in v3 while defining pytest evaluator loading through exact
standalone-file collection rather than generic script execution.
