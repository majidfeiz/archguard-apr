# Repair orchestration schemas v1

- `archguard.repair-run-spec/v1`: immutable baseline, artifact references, roles, budgets, seed,
  human policy and mandatory validation gates.
- `archguard.repair-run-events/v1`: canonical ordered event collection whose individual events are
  SHA-256 chained.
- `archguard.repair-checkpoint/v1`: verified resumable semantic state.
- `archguard.agent-request/v1` and `archguard.agent-response/v1`: provider-neutral capability-bound
  invocation contracts.
- `archguard.human-decision/v1`: run/candidate/checkpoint-bound explicit decision.

Canonical artifacts are compact sorted-key UTF-8 JSON with a terminal newline. They exclude times,
host paths, process/container IDs, durations and temporary names from semantic identity. Normal
artifacts contain references and hashes, never source or raw sensitive logs.
