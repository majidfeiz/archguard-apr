# Architecture profile schema v1

The normative immutable values and invariants are in `domain/architecture_profile.py`.
`architecture_profile_schema_version` is independently versioned as the string `"1"`.

| Canonical field | Value |
| --- | --- |
| architecture_profile_schema_version | `"1"` |
| id | Safe profile ID |
| name | Nonempty single-line name |
| description | Bounded single-line text or null |
| components | Component records sorted by unique ID |
| rules | Specialized rule records sorted by unique ID, including disabled rules |
| assignment | `unassigned` and `ambiguous`: `ignore`, `warn`, `error` |
| profile_fingerprint | Lowercase SHA-256 of semantic fields |

Component: exactly `id`, `selectors`. Selector: exactly `type`, `value`. Rule common fields:
`id`, `type`, `severity`, `enabled`, `description`, `include_type_checking`. Specialized fields:
`source`/`target`, `source`/`allowed`, `source`/`external`, or `components`, respectively for the
four [DSL rules](../architecture/constraint-dsl.md). References must name defined components.
Canonical records include every default. YAML may omit optional defaults and must omit
`profile_fingerprint`; compilation computes it. Canonical JSON requires all fields.

Limits: profile input and canonical output each at most 1 MiB; 1–256 components; 1–256 selectors
per component; 0–2,048 rules; at most 256 component references per rule; 1–256 external selectors
for external rules; IDs at most 128 characters; selector values at most 1,024; names/descriptions
at most 4,096. Limits apply before deduplication. YAML nesting is bounded to 16 levels.

YAML is decoded with `yaml.safe_load`, after token/structure checks. All anchors and aliases are
rejected, as are duplicate mapping keys (at any nesting level), non-string keys, unsafe/custom tags,
unknown fields, invalid types, unsupported schemas and malformed input. YAML booleans and numbers
are not coerced to profile strings. Empty profiles and cyclic structures fail closed.

Canonical JSON is `json.dumps(sort_keys=True, ensure_ascii=True, allow_nan=False,
separators=(",", ":"))` plus one LF, encoded as UTF-8. Components/rules sort by ID;
selectors sort by `(type, value)` and deduplicate; component references sort lexically and
deduplicate. Profile SHA-256 hashes this canonical object with only `profile_fingerprint` omitted.
The trailing LF is part of hash framing. This includes identity, descriptive text, policy and all
rule controls, enabled or disabled. YAML comments, whitespace, mapping/declaration order, source
filename, host data and destination do not enter the fingerprint.

Artifact SHA-256 instead hashes the entire persisted canonical file including the fingerprint.
JSON readers reject duplicate keys, nonfinite numbers, unknown fields, coercions, inconsistent
fingerprints and noncanonical collection structure. JSON mapping order and whitespace may differ
on input. Reads are bounded; writes are atomic. See [engine safety](../architecture/constraint-engine.md).
