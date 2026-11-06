# V2.1B evidence import and readiness verification

The source-free PySnooper-2 fixed-tree identity from GitHub Actions run `41905812267` was validated
and imported on 2026-11-06. This finalization did not trigger that workflow, access a provider, or
execute a scientific repair.

## Evidence chain

- Outer GitHub artifact SHA-256:
  `15e8d9aec02af13cdc3d6563f131a1221f50e1a3e4d3f1303046e003ecfa5032`
- Canonical inner `evidence.zip` SHA-256:
  `bc2bfa9867fdc7ac767c6e090ead058629b08dfc8fc7faa2c0e8feb9c1bcb0e6`
- Archive-manifest fingerprint:
  `5609599c08f34a04c12be3446ddc180b1332a92d0ecfb6adc818151f82fb07b0`
- Imported JSON SHA-256:
  `145ed5cd2e1f005a253b56b4211a6f015a16a95c0f55003102e7d587b79ec16c`
- Identity fingerprint:
  `a7e6c1d87d7366eb2aa6fb77ac0bd314b309471ce2466ffcaa3655e6cfd72fe4`

The outer ZIP contained exactly one regular `evidence.zip`, byte-identical to the separately supplied
canonical inner archive. The inner archive passed the production validator with exactly
`SHA256SUMS`, `cleanup-summary.json`, `manifest.json`, and `tree-identity.json`. Its manifest bound
the pre-import task-manifest fingerprint. A temporary production import was byte-identical to the
tracked JSON, identical reimport was idempotent, and a synthetic contradictory import was rejected
without changing valid evidence.

## Prospective fingerprint migration

- Old PySnooper-2 task-manifest fingerprint:
  `400834ccce3146e41c6f30aedc334b017028b48bc14f7a08608ba86277efeba0`
- New PySnooper-2 task-manifest fingerprint:
  `d06c9c7e182e927e0955e1538133d9185c3918c2da19ff47f05e493d0295417f`
- Reason: `IMPORTED_FIXED_TREE_IDENTITY`

The old fingerprint remains in the imported archive binding, the regenerated manifest, and the
prospective provenance record. This avoids a circular dependency. No historical Phase 12 or Phase
13 artifact or fingerprint was modified.

## Readiness decision

Production preflight reports both PySnooper-2 and PySnooper-3 as `READY`, with no blocker codes.
The frozen fairness, pricing, response-schema, security, sandbox, source-free cleanup, eight-call,
zero-retry, and cost gates remain satisfied. Aggregate `V2_MICRO_PILOT_READY` is therefore `true`.

Readiness is not authorization. `human_authorization_required` remains true; `workflow_triggered`,
`provider_calls_executed`, and `scientific_executions` remain false or zero. The fixed call order is
PySnooper-2 then PySnooper-3, each under `BASELINE`, `GRAPH_ONLY`, `GRAPH_CONSTRAINTS`, and
`FULL_ARCHGUARD`. The maximum reservation is USD 0.1175 per call, USD 0.9400 total, under the USD
1.0000 hard ceiling.

## Verification

The focused V2/archive/patch/architecture suite passed 113 tests. The full non-Docker suite passed
on both Python 3.12.13 and Python 3.13.13: 1,045 passed, one skipped, and three Docker tests were
deselected, with 90.10% combined statement and branch coverage. Ruff format/lint, strict mypy,
JSON/YAML validation, leakage scans, production preflight reproduction, canonical byte regeneration,
package build, and `git diff --check` passed.
