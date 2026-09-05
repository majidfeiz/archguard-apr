# mcp integration (planned)

No integration is implemented or installable in Phase 1. A future adapter will translate host
requests into application use cases and return structured results. Core must not import host SDKs.
External validation and internal orchestration remain independently selectable.

Define repository/worktree authorization, minimum filesystem access, credential isolation,
cancellation and output limits first. Treat repository text and model output as untrusted data.
Require sandboxing and controlled network access before executing code. Never expose secrets,
gold patches or hidden answers. Installation and authentication commands await implementation.
