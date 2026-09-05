# Repository snapshot schema v1

Canonical snapshots are UTF-8 JSON objects with sorted keys, compact separators, `ensure_ascii=True`,
`allow_nan=False` and exactly one trailing LF. Arrays retain the canonical ordering below. Unicode
names are escaped in JSON without Unicode normalization of filesystem paths. No timestamps, raw
source, host paths or environment data are fields. `RepositorySnapshot` and nested frozen dataclasses
in `domain/repository.py` define the typed contract; Pydantic is used only by the boundary decoder.

| Record | Fields and semantics |
| --- | --- |
| RepositorySnapshot | `schema_version` exactly `"1"`, `language` exactly `"python"`, `root_label` exactly `"repository"`, lowercase `repository_fingerprint`, `analysis_options`, `files`, `diagnostics`, `summary` |
| AnalysisOptions | Positive `max_file_bytes`; sorted/deduplicated `excluded_dirs`, `excluded_patterns`, `source_roots`; `include_hidden`, `symlink_policy` (`skip`/`reject`), `fail_fast` |
| SourceFileSnapshot | Normalized `path`, raw `sha256` or null, `byte_size`, `line_count`, optional `module_name`, `package_initializer`, `parse_status` (`parsed`/`failed`/`skipped`), `imports`, `symbols` |
| SymbolSnapshot | `identifier`, `qualified_name`, `kind` (`class`/`function`/`async_function`), `path`, `start_line`, `end_line`, `column`, optional `parent_qualified_name`, `visibility`, ordered `decorators`, `method` |
| ImportSnapshot | `path`, `line`, `column`, `kind` (`import`/`from`), `raw_module`, optional `imported_name`/`alias`, `relative_level`, `target`, `wildcard`, `type_checking` |
| AnalysisDiagnostic | Safe `path` or null, `code`, `severity`, constant source-free `message`, optional `line` and `column` |
| RepositorySummary | Counts described below; validated against contained records |

A read/decoding/syntax failure is `failed`; skipped symlinks, oversized files and nonregular `.py`
entries are `skipped`. Unread/skipped entries have null digest and zero byte/line counts because no
bounded complete contents were acquired. Decoding and syntax failures retain raw byte digests/counts.
Only parsed files have imports/symbols. Directory diagnostics are not source-file records. Excluded
entries are neither candidates nor diagnostics. A directory link with `.py` suffix is a skipped
candidate because it cannot be trusted as a directory without following it. All non-followed links
can produce diagnostics even when not `.py`. Invalid filename paths are omitted and diagnosed with
null path. The snapshot may be partial; a partial fingerprint is not an identity for unread content.

## Ordering and identifiers

Files: ascending normalized relative path, unique. Symbols: `(start_line, column, identifier)`.
Imports: `(line, column, target, alias-or-empty)`. Diagnostics: `(path-or-empty, code, line-or-zero,
column-or-zero)`. Class/function parent names and spans are validated; duplicate definitions are
retained, never overwritten.

Symbol identifier grammar: `symbol:<relative-path>:<qualified-name>@<line>:<column>`.
Qualified names are dotted Python identifiers. Parse the final line/column and qualified-name
separators from the right, allowing colons in a POSIX filename. File paths disambiguate module
conflicts and spans distinguish duplicate definitions. IDs are deterministic but change if a
symbol's position changes. There are no random, timestamp or machine components.

Module names derive from path components minus `.py`; `__init__` is removed. Without source roots,
`src/example/service.py` is `src.example.service`. With `source_roots: [src]` it is `example.service`.
A root equal to a file path produces an empty/invalid derivation. The longest matching configured root wins; order does not matter. Unmatched files retain the full
relative derivation. Namespace-like paths do not require `__init__.py`. An empty derivation or an
invalid identifier/keyword component yields null plus `invalid_module`. Every conflicting file gets
`module_conflict`; all records remain. Different Unicode spellings remain different path identities.

Plain import target is the raw dotted module; from-import target is leading relative dots + module
+ separator (only for a nonempty module) + imported name. Examples: `os`, `pkg.name`, `.sibling`,
`..parent.Thing`, `external.*`. This is textual normalization, not dependency resolution.

## Summary counting

- `discovered_python_files`: number of file records, including failed/skipped candidates.
- `parsed_files`, `failed_files`, `skipped_files`: status partitions, summing to discovered count.
- `total_bytes`: sum of complete raw byte buffers represented by digests (including parse failures).
- `total_lines`: physical raw lines after CRLF and CR map to LF; empty input is zero, final LF adds
  no extra empty line. Other byte separators do not split lines. LF/CRLF changes raw digests.
- `module_count`: number of unique non-null derived names across all candidate records, including
  failed/skipped candidates; this does not imply importability.
- `class_count`, `function_count`, `async_function_count`: all nested/top-level symbols, partitioned
  by kind; sync function count excludes async definitions and includes sync methods.
- `import_statement_count`: distinct `(path, line, column)` positions, so `import a, b` counts once
  and `import a; import b` counts twice.
- `diagnostic_count`: all diagnostic records, including directory and module-policy diagnostics.

## Fingerprint framing

Compute SHA-256 over canonical JSON (same encoding/separators/trailing LF) of:

```json
{"analysis_options": {}, "files": [["relative.py", "raw-sha256"]], "parser_grammar": "python-3.12", "schema_version": "1"}
```

Here `analysis_options` contains every real AnalysisOptions field, not the empty illustrative object,
and `files` is sorted by path with only non-null digests. JSON arrays, quoted strings and object keys
provide unambiguous framing. Settings `strict` affects only CLI exit status and is excluded; all domain
options including fail-fast are included. Content/path/options changes affect identity; excluded
contents, checkout location, discovery order and time do not. Skipped/unread file contents cannot be
fingerprinted and are explicitly omitted. Syntax/encoding failures that were fully read are included.
The artifact SHA-256 is a separate digest over the complete canonical snapshot bytes.
