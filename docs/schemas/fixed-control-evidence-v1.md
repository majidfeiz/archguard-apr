# Fixed-control evidence v1

A fixed-control result is source-free and contains exactly: attempted state, full revision, enum stage,
outcome, optional exit code, bounded duration and test counts, truncation state, normalized failure class,
failure-signature SHA-256, evaluator-selector fingerprint, dependency-environment fingerprint, evaluator
image identity, and optional categorical infrastructure diagnostic.

Stages are `ACQUISITION`, `REVISION_VALIDATION`, `DEPENDENCY_RESOLUTION`, `IMAGE_BUILD`,
`PROJECT_INSTALL`, `TEST_COLLECTION`, `TEST_EXECUTION`, `RESULT_PARSING`, and `CLEANUP`.
The fixed dependency-environment fingerprint must equal the buggy environment fingerprint. A passing
control is attempted, executes the declared selector at the exact fixed revision, exits zero, and has no
infrastructure diagnostic. Raw stdout/stderr, source, test contents and environment dumps are forbidden.
