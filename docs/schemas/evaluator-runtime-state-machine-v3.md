# Evaluator runtime state machine v3

Schema `archguard.evaluator-runtime-state-machine/v3` preserves the v2 state order and strengthens
pytest semantics. For a standalone external pytest fixture, successful exact-node collection is the
authoritative loading operation. That one subprocess produces two explicit ordered transitions:

1. `EVALUATOR_IMPORT_VERIFIED` records that pytest loaded the immutable fixture with exit status zero.
2. `TEST_COLLECTED` records exactly one approved node with separate logical selector, resolved
   selector, and collected-node fingerprints.

Logical selectors must name the reviewed relative fixture exactly. Resolution is confined to the
read-only `/evaluator` mount; absolute paths, traversal, workspace resolution, duplicate nodes, and
selector mismatches fail closed. Standalone pytest files do not require package markers or dotted
module importability. Raw collection output, fixture content, and container paths are not retained.
