# ADR-0008: Accept a narrow textual patch subset

Status: Accepted

Phase 5 supports regular textual add, modify, and delete operations only, with explicit size,
operation, and path limits. Binary, rename/copy, symlink, gitlink, traversal, `.git`, protected, and
ambiguous inputs are rejected before application. Exact bytes are hashed without normalization.
This conservative subset reduces parser ambiguity and prevents repository-metadata mutation.
