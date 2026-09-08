# Deterministic context retrieval

Phase 6 compiles bounded query text into normalized NFKC/case-folded identifiers, hashes raw inputs,
and retains only safe explicit references. Seeds cover paths, traceback frames, modules, node IDs,
symbols, architecture endpoints, changed paths, and lexical graph metadata. Unknown references stay
as source-free diagnostics; ambiguous matches remain multiple explicit seeds.

Traversal is a sorted bounded breadth-first expansion over containment, definition and import edges
in both directions. Cycles cannot amplify candidates because shortest distances are retained.
Scoring components are: explicit path 10000, exact node 9500, traceback 9000, exact module 8500,
exact symbol 8000, architecture endpoint 7800, changed path 7600, lexical 300, relationship 120,
expanded-seed proximity 10% of the strongest contributing seed, distance decay -100 per hop,
independent evidence +50 per additional evidence category, and ambiguity -150.
Components with the same name aggregate. Ties follow ADR-0009.

The source-free manifest records all capped candidates, decisions and conservative costs. The
sensitive bundle merges selected ranges, reopens only snapshot paths with descriptor-relative
`O_NOFOLLOW`, verifies regular-file type, byte size and SHA-256, requires UTF-8, rejects lines over
65,536 bytes, and fails closed after mutation. It never imports or executes repository source.

Offline labels are independently authored node IDs—not gold-patch-derived. MRR is reciprocal first
relevant rank; Hit@K is any hit; Recall@K divides unique hits by unique relevant labels; Precision@K
divides by available ranked results up to K. Values serialize to six deterministic decimal places.
Missing labels and partial manifests make evaluation partial.
