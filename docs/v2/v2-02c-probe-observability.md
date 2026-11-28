# V2.2 capability-probe observability incident

GitHub Actions run `46055379901` at head
`95af0f4c3a679819319a95441f64a5d5cd108286` produced artifact ZIP SHA-256
`2ae80eac5458187cef66dbf0c27e138cac14e8c971d9fc5ee0165ddf0c47b772`. The environment secret was
present, frozen-protocol preflight passed, and the capability-probe CLI started.

The artifact reported `PRE_PROVIDER_BLOCKED`, zero request attempts, zero accepted calls, and zero
scientific executions. Those provider counters are not trustworthy because the old CLI caught every
probe `ValueError` as a pre-provider failure, while the probe could raise `ValueError` after an
adapter response and usage metadata. The run is therefore `HISTORICALLY_AMBIGUOUS`: provider
acceptance, usage, and cost remain unknown. The historical artifact is not changed or reinterpreted.

The repaired probe separates local admission, provider request, provider response, usage
reconciliation, structured-response validation, and optional patch-semantic validation. Returned
usage is reconciled without resetting attempts, accepted calls, tokens, or cost. Patch semantics are
informational and do not define provider capability.

A future request requires the new token
`AUTHORIZE_V2_PROVIDER_CAPABILITY_PROBE_OBSERVABILITY_FIX_1_CALL`. All three earlier probe tokens
are rejected.
