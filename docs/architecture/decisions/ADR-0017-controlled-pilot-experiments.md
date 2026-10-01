# ADR 0017: Controlled pilot experiment boundary

Status: accepted for Phase 12.

Experiment identities, configurations, runs, metrics and ledgers are immutable domain values.
Application services own fairness, scheduling, lexical baseline, blinding and aggregation. Adapters only
load/write artifacts and expose CLI operations. Evaluation split access fails in the domain before any
adapter action. This preserves vendor neutrality and source-free evidence while requiring separate,
explicit adapters for future external/live execution.
