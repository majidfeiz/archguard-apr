# Local low-resource micro-pilot

Status: one real BugsInPy task qualified with limitations; this is not a final evaluation.

The deterministic `eligible-lightweight-lexicographic/v1` selection used seed `12625` and selected
`PySnooper-1` and `PySnooper-2`. Both share the small official buggy revision
`e21a31162f4c54be693d8ca8260e42393b39abd3`, declare Python 3.8.1, and are covered by the MIT license
verified at that revision. Selection did not inspect patch contents, repair success or patch similarity.

The official checkout algorithm copies evaluator tests from the fixed revision into the buggy tree.
Those tests and helper material remained evaluator-only. Fixed source and reference patches remained
gold-quarantined. The agent-visible checkout contains only the buggy archive.

| Task | Three-run baseline | Stability | Evaluator |
| --- | --- | --- | --- |
| PySnooper-1 | Declared test passed three times on the buggy revision | `NOT_REPRODUCIBLE` | Not qualified |
| PySnooper-2 | Same declared `TypeError` and exit 1 in all three runs | `STABLE` | Qualified |

PySnooper-2 required two recorded evaluator adaptations: `python_toolbox==1.3.2` from the task setup
and `six==1.15.0`, an undeclared import of that helper. Qualification verified the buggy failure, a
trusted fixed-revision pass, empty and malformed patch rejection, test-deletion and skip-insertion
rejection, timeout classification, lack of Docker-socket/gold-path/host-secret access, and cleanup.
No provider was called.

Static analysis covered 14 Python modules with no parser diagnostics. Repeated graph construction was
byte-identical at SHA-256 `89e267d0f667e0beac021bca3478465eb5ded9c4b7c013d63e804fd93c013864`;
the graph has 239 nodes and 293 edges. Synthetic context retrieval completed with manifest fingerprint
`5fb24d8aaba88df2c007b7ec435dec09a8c1e481a853c2222ae0128363061e63`.

The profile fingerprint is `e2694d6a8016382036a3670476d75a0ca16d7f9872678156d16fba6de0f441f1`
and its status is `REVIEW_REQUIRED`. Its first evaluation is intentionally partial: 12 of 14 modules
were assigned, while `setup` and `misc.generate_authors` require human disposition. Four rules were
evaluated without violations and the cycle rule was skipped because assignment was incomplete. This is
not approval and the project maintainers have not endorsed the draft.

SWE-bench execution is `SKIPPED_RESOURCE_LIMIT`. No image was pulled: task-image size could not be
bounded without acquiring the gold-bearing dataset payload, and the dataset-specific license remains
unresolved. The micro-pilot succeeds as a qualification exercise without SWE-bench execution.
