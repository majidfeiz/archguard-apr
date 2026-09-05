# Repository graph schema v1

`graph_schema_version` is the string `"1"`, independent of the snapshot schema. The normative typed
fields and invariants are in `domain/graph.py`, `graph_validation.py` and `graph_resolution.py`.
Artifacts contain exactly:

| Field | Meaning |
| --- | --- |
| graph_schema_version | `"1"` |
| snapshot_fingerprint | Lowercase SHA-256 from the input snapshot |
| build_options | `external_names`: `full_module` (default) or `top_level` |
| nodes | Unique records sorted by identifier |
| edges | Unique records sorted by identifier |
| diagnostics | Records sorted by canonical JSON bytes |
| input_partial | Input snapshot's partial status |
| summary | Derived counts, validated against records |
| graph_fingerprint | SHA-256 of the identity object below |

Node fields are `identifier`, `kind`, `file`, `symbol`, `module_name`, `owner_path`.
Unused metadata fields are explicitly null. Repository has no metadata. File metadata has relative
`path`, `sha256`, `byte_size`, `line_count`, `module_name`, `package_initializer`, `parse_status`,
`import_count`, `symbol_count`. Module requires its unique owner path and dotted module name.
External module requires only its name. Symbol metadata is the unchanged Phase 2 SymbolSnapshot.
Node kinds: repository, file, module, class, function, async_function, external_module.

Edge fields are `identifier`, `source`, `target`, `kind`, `import_record`, `resolution`, `occurrence`.
Structural edges use null import/resolution and occurrence 0. Imports use a complete Phase 2
ImportSnapshot, internal/external resolution, and a positive occurrence rank. Kind is contains,
defines or imports. Every endpoint must exist and comply with the documented relationship policy.

Diagnostic fields are `code`, `severity`, `message`, `path`, `line`, `column`, `import_record`,
`resolution`, `occurrence`. Unresolved imports use unresolved/ambiguous status and exact source
locations from the import record. Non-import diagnostics have null locations/record/resolution and
occurrence 0. Messages are fixed by code; incomplete-input severity is warning, other records error.

## Canonical bytes and identities

Canonical JSON uses Python `json.dumps(sort_keys=True, ensure_ascii=True, allow_nan=False,
separators=(",", ":"))`, then one LF, encoded as UTF-8. Enums serialize as strings, tuples as arrays;
no omitted defaults. Reads reject duplicate keys, unknown fields, coercions, unsupported schema,
nonfinite numbers, invalid ordering/references/metadata and inconsistent counts/hashes. Whitespace
and object-key order on input may differ; writing always produces canonical bytes.

Edge identity hashes the canonical object with keys `graph_schema_version`, `kind`, `source`,
`target`, `import_record`, `resolution`, `occurrence`; ID is `edge:<lowercase-sha256>`.
Graph identity hashes the canonical object with keys `graph_schema_version`, `snapshot_fingerprint`,
`build_options`, `nodes`, `edges`, `diagnostics`, `input_partial`. Summary and graph_fingerprint are
excluded because they are derived. Raw artifact SHA-256 instead hashes the entire persisted file.
All hashes include the canonical trailing LF. Paths, time and process state never enter framing.

## Counts

`total_nodes`, `total_edges` count all records. `<kind>_nodes` counts each of seven node kinds;
`containment_edges`, `definition_edges`, `import_edges` count each edge kind. `internal_imports`
and `external_imports` count occurrences, not unique pairs. `unresolved_imports` and
`ambiguous_imports` count import diagnostics by resolution, excluding ownership-only diagnostics.
`diagnostic_count` counts all diagnostics. `partial` is input_partial OR any diagnostics.
`unique_internal_module_dependencies` counts distinct internal (source,target) import pairs,
including self-imports and TYPE_CHECKING edges.

See [behavior and limitations](../architecture/repository-graph.md).
