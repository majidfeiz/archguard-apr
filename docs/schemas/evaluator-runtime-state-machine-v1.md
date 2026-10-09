# Evaluator runtime state machine v1

The source-free record uses schema `archguard.evaluator-runtime-state-machine/v1`. Transitions are
strictly ordered: `PLAN_VALIDATED`, `SOURCE_ACQUIRED`, `SOURCE_IDENTITY_VERIFIED`,
`EVALUATOR_ACQUIRED`, `EVALUATOR_IDENTITY_VERIFIED`, `INSTALLATION_PREPARED`, `SOURCE_MOUNTED`,
`EVALUATOR_MOUNTED`, `PROJECT_IMPORT_VERIFIED`, `EVALUATOR_IMPORT_VERIFIED`, `TEST_COLLECTED`,
`BUGGY_EXECUTED`, `FIXED_EXECUTED`, and `CLEANED`.

Each transition follows an actual operation and contains only its sequence number, state, and a
canonical operation fingerprint. Configuration presence never creates a transition. A missing or
out-of-order operation fails closed and `next_required` identifies the first unreached state.

Mount proof checks exact paths, independent mount identities, read-only source/evaluator mounts,
writable temporary and home paths, fixture identity, absent Docker socket, and disabled execution
network. Evidence never contains fixture bytes, directory listings, source, patches, gold data, or raw
logs. Phase 12.8F.4.2.1 preserves this historical ordering and introduces v2 for explicit writable
filesystem transitions.
