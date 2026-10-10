# Phase 12.8F.4.2.2 external pytest evaluator loading

Baseline: `ef6782c8cb244a4f1760dd4f4c4c70a5468886d4`, version `0.12.8`.

Run `37896070272` successfully reached `PROJECT_IMPORT_VERIFIED` after proving fixture identity,
the repaired tmpfs topology, and read-only source/evaluator mounts. It then stopped at
`EVALUATOR_IMPORT_FAILED`, collected zero tests, ran zero buggy scientific attempts, did not attempt
the fixed control, qualified no task, and remains historical non-imported evidence.

The proven cause was the generic evaluator-import preflight: it executed the standalone pytest file
with `runpy.run_path()` before pytest collection and treated that as package/module import validation.
A reviewed external pytest file does not require dotted-module or package semantics. The repair uses
pytest collection under the execution environment as the loading proof.

The approved logical selector `tests/test_chinese.py::test_chinese` resolves only to
`/evaluator/tests/test_chinese.py::test_chinese`. Resolution rejects absolute paths, traversal,
workspace paths, fixture mismatches, missing selectors, and duplicate/mismatched collected nodes.
Collection must exit zero and report exactly one approved node before the separately fingerprinted
`EVALUATOR_IMPORT_VERIFIED` and `TEST_COLLECTED` transitions are recorded.

The collection environment retains `PYTHONPATH=/workspace`, `HOME=/tmp/home`,
`TMPDIR=/tmp/archguard`, `PYTHONDONTWRITEBYTECODE=1`,
`PYTHONPYCACHEPREFIX=/tmp/archguard/pycache`, and pytest `cache_dir=/tmp/pytest-cache`.
Source, evaluator, and wheelhouse mounts remain read-only and fixture/source identities remain bound.

The security summary's `adapter-registry-v2.json` is a legacy filename containing the active reviewed
`archguard.evaluator-adapter/v3` record; it is not a schema claim. Only PySnooper-1 is enabled. Batch
A, Batch B, and Phase 13 are prohibited, historical runs remain non-imported, and
`phase_13_ready=false`. The artifact name is
`archguard-phase-12-8f4-2-2-pysnooper-1-runtime-canary-<run-id>`.
