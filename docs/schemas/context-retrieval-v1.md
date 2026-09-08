# Context retrieval schemas v1

All JSON artifacts are canonical UTF-8, sorted-key, one-LF documents with strict shape,
duplicate-key/non-finite-value rejection, recomputed fingerprints, bounded symlink-safe reads,
atomic immutable writes, and no host-dependent identity fields.

- `CompiledRetrievalQuery`: normalized terms, safe explicit/traceback/changed references, raw-text
  hashes and source-free diagnostics. All fields except `query_fingerprint` form its identity.
- `RetrievalPolicy`: bounded traversal, inclusion and byte/line/file/symbol/excerpt limits; every
  field except `policy_fingerprint` forms its identity.
- `RetrievalManifest`: method, input fingerprints, seeds, ranked candidates, named scores,
  relationships, decisions and budget accounting. It is source-free.
- `ContextBundle`: sensitive marker, manifest/snapshot/graph identities and ordered excerpts with
  relative path, range, content hash, byte count and content.
- `RelevanceLabels`: strict independently supplied unique node IDs.
- `RetrievalEvaluation`: manifest/label identities, denominators, missing references and exact
  deterministic MRR/Hit/Recall/Precision values.
