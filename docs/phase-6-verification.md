# Phase 6 verification

## Baseline and scope

The authoritative local `main` baseline was
`e1c540b6c47c2b211909274afc87e4cca5a43ada`, version 0.5.0. Its complete suite passed:
374 tests and 96.51% combined statement/branch coverage, with upstream Starlette/httpx and AnyIO
deprecation warnings. Phase 4 commit `009f489c55142185dccf50016bc05ef3f6701b05` and the equivalent
Phase 5 merge (`cf2358d` merged by `e1c540b`) were present. No network Git or GitHub operation
was performed.

Phase 6 updates the package to 0.6.0 and adds only deterministic graph context retrieval: immutable
query/policy/seed/candidate/manifest/bundle/label/evaluation values; narrow artifact, label and source
ports; pure compilation, retrieval, bundling and evaluation services; strict adapters; CLI, examples,
tests, three ADRs, CI smokes and documentation. It adds no LLM, embedding, vector database, semantic
retriever, agent, repair, patch-ranking, execution-feedback or code-execution feature.

## Architecture and identity

The dependency direction remains entrypoints → application → domain. Domain uses standard-library
values only. Application reads no files and invokes no subprocess. Infrastructure owns canonical
artifact I/O, bounded YAML labels and descriptor-relative source access.

Raw problem/error/traceback text is bounded to 1 MiB each. Compilation applies NFKC normalization,
locale-independent case folding, identifier/punctuation splitting, stop-term/duplicate removal and
safe path validation. Raw texts contribute SHA-256 values; their contents do not persist. Query,
policy, manifest, bundle, labels and evaluation have independent schema version 1 fingerprints.

Seed weights are explicit path 10000, exact node 9500, traceback 9000, exact module 8500, exact
symbol 8000, architecture endpoint 7800, changed path 7600 and lexical metadata 300. Expanded nodes
receive 10% of the strongest seed, relationship 120, distance decay -100/hop, +50 for each additional
independent evidence category and -150 ambiguity. All arithmetic is bounded integer arithmetic.
Ranking is descending total score, ascending distance, file/module/class/function/async/external/
repository kind priority, canonical node ID, then repository-relative path.

Traversal is sorted bidirectional BFS over configured contains/defines/imports edges, maximum depth
four. Shortest distance, canonical predecessor relationships, contributing seeds and alternative
shortest-path count are retained. No call edge is invented.

Selection processes rank order and strictly limits files, symbols, excerpts, incremental unique
lines, conservative once-per-file UTF-8 bytes, per-file excerpts and manifest candidates. Overlapping
ranges are charged once and reported as `duplicate_range`; candidates that do not fit are retained
with their exclusion reason. Actual bundle ranges are merged and rechecked against hard limits.

## Privacy and source safety

`RetrievalManifest` is source-free: it contains only fingerprints, relative identifiers, line
ranges, score components, graph evidence, decisions, diagnostics and accounting. It contains no raw
query, traceback, source, absolute path, timestamp, username, hostname or temporary path.

`ContextBundle` is marked `sensitive-source-bearing` and CLI creation refuses without
`--include-source`. Normal creation/inspection output contains metadata only. The reader accepts
only snapshot paths within validated source roots, traverses directory descriptors with
`O_NOFOLLOW`, requires a regular file, verifies exact snapshot byte size and SHA-256 before UTF-8
decoding, rejects lines above 65,536 bytes, and reads only selected ranges. Mutation, deletion,
symlink replacement, directory replacement, invalid encoding, traversal and source-root escape fail
closed. Repository-controlled code was never imported or executed.

## Actual verification

| Check | Actual result |
| --- | --- |
| baseline `pytest` | 374 passed; 96.51% combined |
| final Python 3.12 suite | 399 passed; two upstream warnings |
| final Python 3.13 isolated suite | 399 passed; two upstream warnings |
| statement coverage | 96.47% (3,583/3,714) |
| branch coverage | 90.58% (750/828) |
| combined coverage | 95.40% |
| Phase 6 focused tests | 25 passed |
| architecture subset | 22 passed |
| Phase 5 real-Git regression | 5 passed |
| Ruff format/lint; strict mypy | passed; 152 files / 93 typed source files |
| lock check; frozen sync | passed |
| package build; version; doctor | 0.6.0 sdist/wheel; all required doctor checks passed |
| query/retrieval/inspect/explain | passed; normal output source-free |
| acknowledged bundle and metadata inspection | passed; repeated bundle byte-identical |
| independent-label evaluation/inspection | passed; repeated evaluation byte-identical |
| architecture self-check | complete; 101 modules, 7 rules, zero violations |
| self-hosting retrieval | complete; both Phase 5 target paths reachable; 7 selected; hard budgets respected |
| pre-commit; CFF 1.2; Compose | passed |
| Docker `archguard-apr:phase-6` | passed; image `ab7fd491fc90…b0e25b` |

The focused tests cover immutability, schema/fingerprint revalidation, Unicode and declaration-order
normalization, empty/oversized inputs, unsafe POSIX/absolute/control paths, POSIX/Windows-like
traceback sanitization, every seed category exposed by the contract, ambiguity/unknown diagnostics,
bounded cyclic traversal, direction relationships, exact integer scoring, deterministic ties,
every hard budget, overlap charging, smaller later candidates, strict JSON/YAML decoding, duplicate
keys/labels, NaN, unknown fields, artifact tampering/symlinks/overwrite, exact retrieval metrics,
explicit source acknowledgement, Unicode extraction, mutation/deletion/type/symlink replacement,
invalid UTF-8, oversized lines, leakage prevention and all CLI commands/exit paths.

## Deterministic example

The independently authored labels name the service and repository file/module nodes. The fixed
ranking begins:

1. `file:src/demo/service.py`, score 20150, selected;
2. `symbol:src/demo/service.py:item_names@4:0`, score 9700, duplicate range;
3. `module:demo.service`, score 9600, duplicate range;
4. `file:src/demo/repository.py`, score 8700, selected;
5. `module:demo.repository`, score 1050, duplicate range.

The budget selected 7 excerpts from 6 files and 1 symbol, consuming 25 unique lines and 513
conservatively accounted bytes. Metrics: MRR 1.000000; Hit@1/3/5/10 1.000000; Recall@1 0.250000,
Recall@3 0.500000, Recall@5/10 1.000000; Precision@1 1.000000, Precision@3 0.666667,
Precision@5 0.800000 and Precision@10 0.400000. These are engineering-fixture results, not research
or repair-performance findings.

Canonical artifact SHA-256 values:

- query: `4ba00642928579e1339d7455654f59ba767b702f80619213219120bfbbf91d36`;
- manifest: `824f4d653f43c6890916ff6de6f91891b296e9b739e14b1dc48dd909f9d6258d`;
- sensitive bundle: `749eb2d973d16614ad17e3cdaac3ef04b7de85f804026ddff4e9b50ec4212ccb`;
- evaluation: `1b8b2646f23cc2ba2268185960e79001c7d9e536982564cd6790abea86240e42`.

Semantic fingerprints were query
`d074c17e110eef20cf28133f844139c91d740b8fccfd1f271cc2d9e86da52a4c`, manifest
`44468e07123c5eec5d2c96847b1b82f3f987c3141e3c5ac628ca5864abb82d9d`, bundle
`8a4af65ccc5d1cdf5745f1fb6cddd0d2640e8dcb4b52b2941734629e45db8736`, labels
`92363a46c557b6036f4a09124001f94cecc19e9f438dfcbeec7857d0ab91f58e` and evaluation
`055c45715dc6b92cad4c812ef3d1cc162ffaa11e9fe140cdb8fdf3a1a1b6481c`.

## Engineering workload and limitations

The fixed 100-module workload produced 203 graph nodes, 202 candidates, 10 selected excerpts, 19
source lines/371 bytes, a 194,898-byte manifest and 2,695-byte bundle. Observed local stages were
0.000142 s query compilation, 0.011283 s combined seed/expansion/scoring/budget selection,
0.001741 s extraction, 0.002134 s manifest serialization, 0.000036 s bundle serialization and
0.000134 s evaluation. Timings are environment observations outside canonical identities, have no
CI threshold, and make no scientific claim.

This phase is Python-metadata retrieval only. It deliberately has no semantic/vector baseline,
dynamic call graph, tokenizer budget, runtime validation or functional-correctness claim. Static
metadata can miss dynamic imports and reflection. Conservative whole-file byte charging may select
less context than exact pre-reading could, which preserves the hard boundary and source-free
retrieval phase. Generated-file recognition is path-policy based rather than content inference.
