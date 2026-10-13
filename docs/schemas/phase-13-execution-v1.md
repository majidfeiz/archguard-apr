# Phase 13 source-free execution schemas

`archguard.phase-13-execution/v1` records frozen identity and revision fingerprints, condition,
request/context/response/patch hashes, bounded patch counts, architecture and evaluator categories,
provider-reported usage, Decimal cost, terminal classification, duration bucket, and cleanup state.
It excludes source-bearing content and host paths.

`archguard.phase-13-manifest/v1` canonically aggregates completed ordinals, attrition, total calls,
observed cost, stop reason, result hashes, and the population/protocol/provider bindings.
`archguard.phase-13-cost-state/v1` is atomically replaced before and after attempts.
`archguard.phase-13-cleanup/v1` reports only whether owned resources were removed. JSON is sorted-key
UTF-8 with one trailing LF; SHA-256 fingerprints cover those canonical bytes.
