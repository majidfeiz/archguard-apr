# Isolated patch validation

Phase 5 performs `snapshot → graph → report` first on an exact baseline commit and then on the same
detached worktree after a candidate patch is applied. Identical analysis, graph, and profile values
are used on both sides. Graph construction consumes only validated snapshots and constraint
evaluation consumes only validated graphs.

The accepted format is an exact-byte-fingerprinted (`SHA-256`) textual Git unified diff containing
regular-file add, modify, or delete operations. Limits are 4 MiB, 256 operations, and 512 UTF-8 bytes
per path. Empty, malformed, NUL-containing, binary, rename/copy, symlink, gitlink, duplicate,
absolute, traversal, `.git`, control-character, protected, and out-of-allowed-root targets are
rejected with stable codes. LF and CRLF inputs retain distinct fingerprints; bytes are never
normalized. Applicability is separately checked against the bound commit.

Persisting violations cannot use Phase 4 violation IDs because those include graph fingerprints.
Dependency semantic keys contain rule ID, category, source module ID, and target module ID. Cycle
keys contain rule ID, category, and sorted participant module IDs. Evidence locations, edge IDs,
counts, graph/patch fingerprints, and discovery order are excluded. Persisting entries retain both
evidence values. Duplicate semantic keys are rejected deterministically.

The architecture gate fails for an introduced error or an incomplete comparison. Existing errors
that persist do not alone fail it; warnings and informational violations remain reported. Patch
application, comparison completeness, architecture outcome, and workflow completion are independent
fields.

Git operations use argument arrays, a 30-second timeout, bounded output, non-interactive behavior,
and `core.hooksPath` set to the null device. Commands are `rev-parse`, `symbolic-ref`, `write-tree`,
read-only status/list operations, `worktree add --detach --no-checkout`, detached `checkout`,
`apply --check`, `apply`, and `worktree remove --force`. Checkout and apply occur only in the adapter
created temporary worktree. Submodules are never initialized. Cleanup unregisters the worktree and
deletes only the verified adapter-created temporary parent, including on exceptions.

Canonical UTF-8 JSON has sorted keys, compact separators, ASCII escaping, and one trailing LF.
Artifacts exclude source, patch text, raw Git output, timing, timestamps, host identity, and local or
temporary paths. Fingerprints cover the complete source-free value except their own fingerprint
field. Optional expected artifact SHA-256 protects consistency, not authenticity against malicious
rehashing.

Known limitations: only Python analysis and the narrow diff subset are supported; no rename/copy,
binary, symlink, gitlink, or submodule mutation is accepted. Dynamic imports may remain unresolved,
and generated or unsupported file types may be outside analysis. Phase 5 executes no candidate code
and makes no behavioral-correctness claim.
