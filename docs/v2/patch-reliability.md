# Patch reliability boundary

The V2 extractor accepts a raw unified diff, exactly one Markdown `diff`/`patch` fence with no
surrounding prose, or one strict structured response. It removes one fence and converts CRLF to LF;
it does not infer paths, create hunks, repair semantics, or accept multiple candidates.

Ceilings cover input bytes, file operations, hunks, lines, paths, identifiers, and rationale. The
existing Phase 5 inspector remains authoritative for unified-diff grammar, safe relative paths,
regular-file modes, supported add/modify/delete operations, and policy roots. Application remains in
a detached temporary worktree. Evidence contains hashes and stable diagnostics, not patch text.

Synthetic fixtures are author-owned and contain no benchmark, provider, third-party, secret, or gold
material. A valid fixture demonstrates format acceptance only, not correctness or effectiveness.
