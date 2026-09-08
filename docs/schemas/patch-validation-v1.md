# Patch validation schemas v1

Candidate patch metadata records exact-byte SHA-256, byte size, sorted add/modify/delete operations,
binary presence, fixed diagnostics, and acceptance. Architecture delta records baseline commit,
profile/snapshot/graph/report fingerprints, introduced/resolved/persisting violations, summaries,
completeness reasons, gate result, and its fingerprint. The complete validation result embeds both,
repository-state proofs, explicit lifecycle booleans/status, stable diagnostic codes, and a result
fingerprint. Readers enforce strict typed shape, duplicate-key rejection, canonical form, schema and
fingerprint validation, bounded regular-file reads, symlink rejection, and optional raw SHA-256.
