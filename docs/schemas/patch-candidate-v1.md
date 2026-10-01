# Patch candidate v1

`archguard.patch-candidate/v1` records run/task identity, round and parent, agent/invocation/raw-patch
references, normalized and semantic hashes, paths, line counts, bounded intent/assumptions and
sensitivity. The trusted parser accepts only UTF-8 unified diffs beginning at byte zero. Prose,
Markdown fences, NULs, binary patches, unsafe modes, rename/copy, absolute/traversal paths and
malformed hunks are rejected. A candidate is untrusted until every deterministic gate passes.
