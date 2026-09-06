# Development

Use Python 3.12 and `uv sync --frozen`. Run `make check`, `uv build`, CLI smoke commands,
`docker compose config` and Docker build. CI checks both supported Python minor versions.
Use pre-commit. `uv lock --check` verifies consistency; review intentional `uv lock` updates.

Configuration: environment > current-directory .env > explicit YAML/constructor > defaults.
Loading creates no directories. Doctor probes the nearest existing output parent with a temporary
file; this does not guarantee future writes or isolation.

Call `configure_logging` explicitly. It configures the ArchGuard logger without changing root
handlers. Pass `extra={"experiment_id": ..., "run_id": ...}` for context. UTC logs redact labeled
tokens, keys, secrets, passwords and authorization values including exceptions. This cannot detect
arbitrary bare credentials: never log provider payloads or secrets directly.

Canonical experiment JSON has sorted keys; array order is preserved. Domain timestamps normalize
to UTC; boundary TypeAdapters can serialize immutable dataclasses. Relative paths reject Windows
and POSIX traversal but do not sandbox symlinks. No untrusted-code runner exists.
AST tests resolve relative imports and forbid dynamic core loading. Ruff uses E/F/I/UP/B.

Narrow mypy suppressions exercise invalid typed inputs and frozen-dataclass mutation guards; production code
has no type-check suppression.


## Phase 2 verification

Run the full `uv run pytest` suite for the mandatory 90% combined coverage gate. For focused AST
architecture checks use `PYTEST_ADDOPTS=--no-cov uv run pytest -m architecture`; a structural subset
cannot measure whole-program behavioral coverage. This does not change the full-suite threshold.
Test fixture `.py.txt` templates are copied into temporary repositories without import/execution;
size-specific, encoding and symlink cases are generated during tests. Examples are tiny real modules.
Run the external-output example twice and compare bytes and SHA-256. Inspect the complete artifact
for host/source leakage and validate source manifests before/after. See the schema and ADR-0003.

Analysis settings are under YAML `analysis:`. Collection overrides replace defaults. Nested environment
keys use double underscores and array values use JSON, e.g. `ARCHGUARD_ANALYSIS__SOURCE_ROOTS='["src"]'`.
Explicit CLI `--source-root` wins over settings for that invocation; strict is enabled by either flag
or configuration. Strict only changes exit status and is excluded from fingerprint options.
The optional benchmark script reports local engineering timing, not a scientific performance result.
Existing upstream Starlette deprecation warnings and baseline Node.js Action warnings are non-blocking;
Action versions have not been guessed or changed in Phase 2.

## Graph verification

Run `make graph-smoke` and `make graph-benchmark`; the latter is an engineering measurement without
a timing assertion. Graph tests cover resolution, multigraph occurrences, canonical identity, corruption,
source-read isolation, path safety and deterministic queries. See [Phase 3 verification](phase-3-verification.md).

## Phase 4 verification

Run `make architecture-smoke`, `make architecture-self`, `make architecture-benchmark`, and all
existing checks. Docker documentation uses `docker build -t archguard-apr:phase-4 .` (package 0.4.0).
CI retains both Python minor versions, package/Docker builds and previous graph smoke commands.
Conformance smoke output stays in `/tmp`; no artifacts are uploaded. Self-hosting declares the
independent example source root in `configs/architecture-self.yaml` to avoid invalid module names.

Tests cover profile safety/limits, assignment, all four rules, aggregation, evidence invariants,
partial status, canonical identity, persistence failure cleanup and CLI outcomes. Full-suite coverage
must remain at least 90%; use the established `PYTEST_ADDOPTS=--no-cov` only for the architecture subset.
See [actual Phase 4 verification](phase-4-verification.md). No tag/release or automatic merge is part
of the Phase 4 workflow.
