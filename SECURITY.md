# Security policy

Phase 1 has no untrusted-code runner or public authenticated API. Bind the health API locally.
Report vulnerabilities through GitHub private vulnerability reporting if enabled, or request
a private maintainer contact through the owner’s profile without publishing exploit details.
TODO: verify a dedicated reporting channel and support policy before operational release.

Future builds/tests execute arbitrary code. Before enabling them, implement isolation, resource
limits, network restrictions, filesystem/symlink containment, credential separation and output
sanitization. Timeouts are not sandboxes. Treat repository text/model output as untrusted.
Never expose gold patches, hidden answers, tokens or personal data unintentionally.
# Phase 5 patch threat model

Candidate patches are untrusted. Bounded static inspection rejects traversal, absolute and `.git`
paths, controls, malformed headers/hunks, duplicate operations, binary payloads, symlink/gitlink
modes, rename/copy metadata, and resource-limit violations. Git receives argument arrays only;
hooks, prompts, network, and submodule initialization are disabled or absent. Application occurs only
inside an adapter-created detached temporary worktree, and state proofs detect original repository
changes. Cleanup never accepts a caller-selected deletion root and does not expose temporary paths.
Canonical artifacts omit source, patch hunks, raw Git output, host details, and timestamps.
