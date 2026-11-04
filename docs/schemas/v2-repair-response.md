# V2.1 repair-response contract

Schema identifier: `archguard.repair-response/v2.1`.

The response is one UTF-8 JSON object with exactly these fields: `schema_version`, `task_id`,
`candidate_id`, `unified_diff`, `declared_changed_paths`, and optional `rationale_summary`. Unknown
or duplicate fields are rejected. One response represents one candidate only; commands, tool calls,
and executable prose are not fields and cannot be accepted.

Identifiers are non-empty, trimmed strings of at most 256 UTF-8 bytes. The optional source-free
rationale is at most 2,048 bytes. The response and patch are bounded to approximately 4 MiB.
Declared paths are unique, sorted, relative POSIX paths and must exactly equal the paths parsed from
the diff. Absolute, traversal, Git metadata, control-character, symlink, gitlink, submodule, binary,
rename, and copy operations fail closed. Empty, no-op, malformed, or multiple patches are rejected.

The domain value is immutable and provider-neutral. Infrastructure performs strict decoding and
passes accepted bytes to the existing Phase 5 inspector. Provider prose is data and is never
executed. Raw source-bearing responses are not written to normal evidence artifacts.
