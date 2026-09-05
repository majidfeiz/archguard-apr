# Deterministic Python repository analysis

Phase 2 adds local read-only structural analysis and canonical artifacts. It does not infer layers,
build graphs, resolve imports, evaluate constraints, call models, execute code or repair repositories.
The HTTP adapter remains health/readiness/version only; analysis is CLI-only as a transport and is
also callable through the Python application use case. Remote path authorization remains undesigned.

## Boundaries

`AnalyzeRepository` accepts neutral options and uses `RepositoryAnalyzerPort` and
`AnalysisArtifactWriterPort`. `InspectRepository` uses `AnalysisArtifactReaderPort`.
The analyzer returns an immutable domain snapshot rather than the Phase 1 persisted artifact.
This intentionally breaks the placeholder analyzer signature at 0.2.0. ArtifactReference adds an
optional SHA-256 field, defaulting to None for existing callers. Architecture and repair ports remain
future contracts. No runtime dependency was added.

Local discovery, reading, AST extraction and hashing live in infrastructure behind the analyzer
port; canonical serialization/validation and atomic persistence are separate replaceable adapters.
The application does no filesystem I/O; CLI only wires dependencies and translates options/results.

## Discovery and safety

Only case-sensitive `.py` suffixes are candidates. Directory names are excluded at every depth;
patterns use `fnmatchcase` on the full normalized relative POSIX path, where `*` can match `/`.
A matching directory is pruned. Defaults exclude `.git`, `.venv`, `venv`, `env`, `__pycache__`,
`.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `.tox`, `.nox`, `build`, `dist`, `site-packages`,
`node_modules`, `benchmark_checkouts`, `benchmark checkouts`, and `experiments/results`.
Custom lists replace defaults; include the defaults explicitly when extending them. `.gitignore`
is intentionally not parsed. Hidden files and directories are omitted unless enabled.

Root must exist and be a directory. A symlink supplied as root is rejected. Source symlinks,
including directory and external links, are never followed: `skip` emits a warning; `reject` aborts
with a path-policy error. Exclusions take precedence, so excluded links are not inspected.
Discovery uses `os.fwalk(follow_symlinks=False)` and opens files relative to live directory
descriptors with `O_NOFOLLOW | O_NONBLOCK`. Only regular files are read. Platforms lacking these
capabilities fail closed; Phase 2 local analysis supports Unix (tested on macOS and Linux CI),
not a less-safe Windows fallback. Canonical path framing is host-independent.

Control characters, surrogate filename bytes and non-normalized/traversal paths are rejected.
Rejected filenames are not echoed; diagnostics have null paths when no safe path can be recorded.
No repository code is imported, evaluated, executed, installed or launched in a subprocess.
Tests compare manifests of paths, types, content hashes and link targets before/after analysis.
A source file swapped to an outside symlink before opening is rejected by the kernel.

The target and output parent must be quiescent during a run. This is not a transactional filesystem
snapshot, hostile concurrent filesystem mutation sandbox, memory-isolated parser, or global resource
quota. Hard links and mounted directories are not provenance boundaries. Per-file size limits bound
reads; deeply nested/large repositories may still consume significant memory or descriptors.
Run against an immutable checkout for published research artifacts.

## Source and failure policy

Raw bytes are hashed with SHA-256. `tokenize.detect_encoding` honors UTF-8/BOM and standard Python
encoding cookies; decoding errors get constant source-free diagnostics. Maximum raw size defaults
to 1 MiB and is checked before opening and with a bounded read before parsing. `ast.parse` uses the
Python 3.12 grammar on both supported interpreter minors. It does not execute decorators/annotations.

Recoverable failures produce ordered diagnostics and collection continues. `fail_fast: true`
aborts on the first error without a partial artifact. CLI default returns 0 with visible `partial`
status if any diagnostics exist. `--strict` or `analysis.strict` exits 1 after reporting/persisting
when error diagnostics exist. Warning-only skips do not fail strict mode.
Exit 2 means invalid root/arguments/configuration/schema. Exit 3 means path-policy rejection.
Unrecoverable analysis or artifact I/O exits 1. Exceptions never print source lines or host paths.

## AST conventions

Classes, sync/async functions and nested definitions are recorded. Spans start at `class`/`def`,
not the decorator; end lines are inclusive. Columns are zero-based UTF-8 AST byte offsets.
Direct class children are methods; decorators named exactly `staticmethod`, `classmethod` or
`property` refine classification (in that precedence if combined). No decorator binding inference
is attempted. Safe dotted decorator callable names are retained; arguments and arbitrary expressions
are omitted. Imports are one record per alias; statement counts deduplicate file/line/column.
`TYPE_CHECKING` and `typing.TYPE_CHECKING` positive if-bodies are marked syntactically; nested bodies
inherit context, else-bodies do not. Aliases, rebinding, compound/negative guards are not resolved.

Visibility is naming convention only: leading `__` without trailing `__` is private, any other
leading `_` is internal (including dunder names), otherwise public. This is not access control.

## Reproducibility and limits

See [snapshot schema](../schemas/repository-snapshot-v1.md) for exact fields/counts/framing.
Ordering is lexical paths, then AST spans and names, then diagnostic keys. No absolute host path,
contents, environment, username, hostname or current timestamp enters canonical output.
Names and paths are structural metadata and can themselves be sensitive; do not publish artifacts
from private source without review. Digests do not attest to semantic correctness or architecture.

Analysis never writes to the target, even excluded directories. Output must be external with an
existing parent; traversal and symlink destinations are rejected. Parent aliases are resolved before
containment checks. Persistence uses a same-directory temporary file, flush/fsync and atomic replace,
with cleanup on failure. Repeated writes replace the requested regular artifact. References report
only the basename and SHA-256; users already know the requested output location.
Inspect accepts at most 64 MiB and validates types, enums, field shape, ordering, IDs, spans, counts,
module derivation, required diagnostics, fingerprint and optional raw artifact hash. Unknown fields,
duplicate JSON keys, unsupported versions and malformed input are rejected. It cannot rederive AST
facts without original source. Fingerprints are integrity identifiers, not signatures.

## Engineering guardrail

`uv run python scripts/benchmark_repository_analysis.py` generates 500 deterministic small modules
in a temporary directory and reports file count/duration. It is explicitly invoked, with no flaky
wall-clock CI threshold, and is not scientific performance evidence. Expected work is approximately
linear in visited paths and source size plus lexical sorting; metadata validation is linear apart
from sorting and the configured pattern/source-root factors.

Implementation references: [Python fwalk](https://docs.python.org/3.12/library/os.html#os.fwalk)
and [encoding detection](https://docs.python.org/3.12/library/tokenize.html#tokenize.detect_encoding).
