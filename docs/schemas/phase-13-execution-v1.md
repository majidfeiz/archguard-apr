# Phase 13 source-free execution schemas

`archguard.phase-13-execution/v1` records frozen identity and revision fingerprints, condition,
request/context/response/patch hashes, bounded patch counts, architecture and evaluator categories,
provider-reported usage, Decimal cost, terminal classification, duration bucket, and cleanup state.
It excludes source-bearing content and host paths.

`archguard.phase-13-manifest/v1` canonically aggregates completed ordinals, attrition, total calls,
observed cost, stop reason, result hashes, and the population/protocol/provider bindings.
`archguard.phase-13-cost-state/v1` is atomically replaced before and after attempts.

Continuation uses `archguard.phase-13-checkpoint/v1`, a canonical source-free record binding the
reviewed archive, incident decision, exact completed execution prefix, provider-call ledger, carried
cost, and remaining frozen ordinals. A provider-call identity is created for a transmission, never
for cost reservation. Resumed execution records carry that identity; imported historical execution
bytes remain unchanged and are linked through the checkpoint call ledger.
`archguard.phase-13-cleanup/v1` reports only whether owned resources were removed. JSON is sorted-key
UTF-8 with one trailing LF; SHA-256 fingerprints cover those canonical bytes.
