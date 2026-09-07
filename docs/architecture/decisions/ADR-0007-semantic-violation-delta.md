# ADR-0007: Match before/after violations by semantic identity

Status: Accepted

Phase 4 violation IDs include graph identity and therefore change after unrelated edits. Phase 5
uses rule/category/module semantic keys, with sorted cycle members, and excludes locations, counts,
edge IDs, and fingerprints. Duplicate keys fail rather than relying on discovery order. Persisting
values retain baseline and candidate evidence for inspection.
