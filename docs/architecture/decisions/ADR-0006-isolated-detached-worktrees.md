# ADR-0006: Validate patches in isolated detached worktrees

Status: Accepted

Candidate input is untrusted and the original repository is scientific evidence. Validation binds a
full commit, requires a clean original worktree, captures state proofs, and uses a temporary detached
Git worktree. Hooks are disabled, submodules are untouched, subprocesses are bounded, and cleanup is
unconditional and idempotent. This avoids checkout, staging, stash, reset, or patch application in
the original repository. It costs temporary disk space and rejects dirty repositories.
