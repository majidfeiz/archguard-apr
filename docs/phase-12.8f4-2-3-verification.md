# Phase 12.8F.4.2.3 external selector resolution

Baseline: `c20a33aa5971f2190c2b2cb8cb48fd88ed3c3c3f`, version `0.12.8`.

Run `38035903312` reached `PROJECT_IMPORT_VERIFIED` and stopped with
`EVALUATOR_SELECTOR_NOT_FOUND`. Collection count was zero, process return code was not retained, no
buggy or fixed scientific attempt ran, and the source-free artifact remains historical and
non-imported.

## Proven cause and bounded conclusion

The artifact's applied-selector fingerprint equals the current runtime selector
`/evaluator/tests/test_chinese.py::test_chinese`; its mount probe also proved the evaluator fixture
existed with the reviewed SHA-256. Therefore the evidence does **not** support claiming that a string
replacement produced `/workspace/tests` or a duplicated path. Because raw pytest output was
intentionally excluded and the preflight discarded the subprocess return code, the lower-level reason
cannot be recovered from that artifact alone.

An outside-repository reproduction used the byte-identical fixture (SHA-256
`7a3d64cd702fdfa1eba8c08ac3c8934948a3ef0178f141c1f5599307c1fe59f3`), fixed revision, Python
3.8, pytest 5.4.3, and the required absolute runtime selector. Pytest accepted the physical path but
failed while loading the evaluator because `test_chinese.py` performs a relative import and the
quarantine contains no reviewed package/dependency material. Pytest then appended a selector-not-found
footer. The current classifier checks that footer before `ImportError`, proving why run 38035903312
reported the wrong `EVALUATOR_SELECTOR_NOT_FOUND` category.

The exact code-level defect is nevertheless provable: selector resolution accepted the whole adapter
instead of the four explicit verified inputs, did not bind logical, physical, and runtime identities
together in the execution plan, reverified the physical fixture only after collection, and converted
collection failures into a diagnostic with a null process return code. This left the external selector
contract under-specified and masked the evaluator dependency/package failure. The repair prioritizes
import failures over pytest's secondary selector footer, so the next canary fails closed as
`EVALUATOR_DEPENDENCY_MISSING` unless reviewed dependency material is separately approved.

The repair introduces one deterministic pytest resolver with explicit inputs. For the unchanged
reviewed adapter its identities are:

- logical selector: `tests/test_chinese.py::test_chinese`
- physical fixture: `/evaluator/tests/test_chinese.py`
- runtime selector: `/evaluator/tests/test_chinese.py::test_chinese`

Absolute logical paths, traversal, alternate files, duplicated prefixes, empty nodes, non-pytest
frameworks, and mount roots other than `/evaluator` fail closed. The physical regular non-symlink file
and SHA-256 are checked inside the isolated container before pytest collection. Collection retains
only selector/node fingerprints, fixture SHA-256, exit code, exact count, bounded duration, and output
truncation status. Raw output, environment dumps, source, and fixture contents are excluded.

The registry file remains `adapter-registry-v2.json` because its top-level schema is still
`archguard.evaluator-adapter-registry/v2`; it contains reviewed adapter records using
`archguard.evaluator-adapter/v3`. The security scan inventory is tested against those exact filenames,
so renaming it to v3 would misstate the registry schema.

Only PySnooper-1 is enabled. Batch A, Batch B, and Phase 13 are prohibited, all earlier failed runs
remain non-imported, and `phase_13_ready=false`. Local tests cannot establish qualification; that
requires the Linux x86 GitHub Actions artifact
`archguard-phase-12-8f4-2-3-pysnooper-1-runtime-canary-<run-id>`.
