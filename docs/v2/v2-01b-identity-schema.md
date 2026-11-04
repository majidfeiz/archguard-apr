# V2.1B fixed-tree identity schema

`archguard.v2-fixed-tree-identity/v1` is a canonical, source-free record of one authorized Git
commit's root tree. It binds the exact repository, requested and resolved 40-character revision,
Git object format, root tree object ID, SHA-256 of the raw recursive NUL-delimited tree listing,
entry count, bounded acquisition size, runner identity, cleanup result, and explicit negative
execution flags. Its `fingerprint` is SHA-256 over canonical JSON excluding that field.

The flat ZIP allowlist is exactly `manifest.json`, `tree-identity.json`, `cleanup-summary.json`, and
`SHA256SUMS`. JSON is sorted-key UTF-8 with one trailing LF. The manifest binds the existing
PySnooper-2 task-manifest fingerprint and member hashes. The checksum file binds all three JSON
members. Import validation rejects unknown fields, noncanonical JSON, duplicate keys or members,
unsafe member types or names, excess sizes or compression, inconsistent hashes, forbidden activity,
failed cleanup, leakage markers, and identity contradictions.

A Git tree identity proves content identity for the referenced Git object. It does not establish
correctness, safety, license ownership, or a successful repair.
