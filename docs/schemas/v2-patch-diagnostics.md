# Prospective V2 patch diagnostics

Schema identifier: `archguard.patch-diagnostic/v2.1`. This taxonomy is prospective V2 engineering
evidence. It does not alter the historical Phase 13 terminal classification `invalid_patch`.

Every diagnostic has a separate stable `stage` and `code`. Its SHA-256 fingerprint covers only the
schema, stage, and code. It cannot contain source lines, prompts, raw responses, secrets, host state,
paths, gold data, or environment dumps.

Stages are `response_parsing`, `patch_extraction`, `diff_validation`, `policy_validation`,
`patch_application`, `architecture_validation`, and `evidence_validation`.

Stable codes are: `NO_PATCH_FOUND`, `MULTIPLE_PATCHES_FOUND`, `AMBIGUOUS_RESPONSE`,
`RESPONSE_SCHEMA_INVALID`, `PATCH_TOO_LARGE`, `MALFORMED_DIFF_HEADER`, `TRUNCATED_DIFF`,
`UNSUPPORTED_PATCH_OPERATION`, `UNSAFE_PATH`, `DECLARED_PATH_MISMATCH`,
`PATCH_CONTEXT_MISMATCH`, `PATCH_APPLICATION_FAILED`, `NO_EFFECTIVE_CHANGE`, `POLICY_REJECTED`,
`ARCHITECTURE_REJECTED`, and `EVIDENCE_CONTRADICTION`.

Downstream application, policy, and architecture stages may emit the reserved codes even when the
extractor does not. Consumers must compare enum values, not messages.
