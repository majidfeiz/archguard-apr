# Phase 13B frozen experiment runner

Phase 13B prospectively amends the exploratory protocol to one repetition of each fixed pair, in
this order: PySnooper-2/baseline, PySnooper-2/archguard, PySnooper-3/baseline,
PySnooper-3/archguard, black-4/baseline, and black-4/archguard. Baseline receives the matched task
and source budget without architecture treatment; ArchGuard receives the frozen, source-free
architecture treatment. Candidate validation and the trusted evaluator remain identical.

The runner is sequential. It reserves worst-case cost before every call, stops new work at USD 4.00,
rejects any projected total above USD 4.50, permits one retry only for timeout, connection, 429, or
provider 5xx, and has no fallback, replacement, or extra repetition.

Live CLI:

```bash
uv run archguard experiment run-frozen \
  --population research/population/exploratory-feasibility-v1.json \
  --protocol research/protocol/exploratory-feasibility-v2.json \
  --provider-config configs/experiments/phase13-provider.json \
  --output /tmp/archguard-phase13-evidence \
  --acknowledge-provider-cost --acknowledge-source-processing
```

Workflow dispatch requires `confirm_phase_13=RUN_FROZEN_PHASE_13`; setting
`execute_scientific_run=false` performs offline preflight only. The output allowlist is
`cost-state.json`, `execution-1.json` through `execution-6.json`, `manifest.json`, and
`cleanup.json`. Unknown artifacts are rejected. Prompts, responses, patch text, source, evaluator
material, logs, secrets, absolute paths, and external checkouts are never persisted or uploaded.

Source is acquired at immutable revisions with hooks, LFS smudging, and submodules disabled. Patches
cross the strict unified-diff boundary and run only in owned temporary source. Tests are selected by
reviewed adapters and run in the network-disabled, non-root, read-only, capability-dropped Docker
sandbox. Controlled cost or infrastructure stops produce valid partial, source-free evidence; they
do not authorize replacement runs. Implementation tests use fake providers and are not scientific
results.
