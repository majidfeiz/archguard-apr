# Sandboxed execution feedback

Phase 7 runs an identical trusted plan against detached baseline and patched worktrees. Each is
copied to a fresh unpredictable sandbox-owned directory; the original repository is never mounted.
Only Docker is invoked on the host. There is no local-process fallback.

Docker runs without networking or stdin, with a read-only root, UID/GID 10001, no capabilities,
`no-new-privileges`, bounded memory/CPU/PIDs, and bounded `noexec,nosuid,nodev` `/tmp`. Only the copy
is mounted; the original and Docker socket are not. Named containers are forcibly removed on every
outcome. Only explicitly allowlisted environment values and controlled constants cross the boundary.

Docker Engine, daemon, kernel, image contents and runtime are trusted computing base components. A
container is not equivalent to a hardened virtual machine. Unsupported isolation fails closed.

Normal artifacts contain hashes, states, normalized test identities and artifact-presence flags—not
raw output, source, temporary paths, container IDs, timestamps, PIDs or durations. Raw logs are not
persisted. Redaction cannot discover every secret, so sensitive-log persistence is omitted entirely.

## Evidence and policy

Evidence distinguishes passed, failed, timed out, cancelled, infrastructure error and invalid result.
JUnit identities use a safe repository-relative file or suite/class plus name. Missing, malformed or
duplicate JUnit results are invalid evidence. Functional deltas classify `fixed`, `regressed`,
`persistent_failure`, `passed_both`, `candidate_only`, `baseline_only` and `status_changed`.

The default rejects regressions, infrastructure/timeout/incomplete evidence, missing baseline tests
and persistent failures. Plans may allow persistent failures. Declared targets require a matching
fix. Added tests are not fixes. Combined reports keep patch applicability, architecture acceptance,
functional acceptance and infrastructure health separate; all must pass. Architecture acceptance
does not prove functional correctness, and selected tests do not prove complete correctness.

## CLI

```text
archguard execution plan validate --plan PLAN
archguard execution plan inspect --plan PLAN
archguard execution compare --repo REPO --baseline REV --patch PATCH --plan PLAN \
  --architecture-profile PROFILE --output RESULT.json
archguard execution result inspect --result RESULT.json
archguard execution result tests --result RESULT.delta.json --state regressed
```

Exit codes: 0 accepted, 1 completed/rejected, 2 invalid input, 3 infrastructure, 4 partial evidence.
