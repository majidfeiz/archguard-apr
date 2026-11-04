# V2.1A internal security review

This is a fresh internal review pass, not an independent third-party audit. It reviewed the future
path from provider request construction through strict response extraction, Phase 5 inspection,
detached worktree application, architecture evaluation, Docker tests, source-free evidence, and
cleanup.

## Confirmed safe

- Provider tools, parallel calls, web/file search, hosted shell, code interpreter, and computer use
  are disabled by the prospective plan. The response is restricted to
  `archguard.repair-response/v2.1`; prose and candidate commands are never executed.
- The extractor rejects invalid UTF-8, ambiguous/multiple/oversized responses, traversal and absolute
  paths, binary patches, rename/copy, symlink and gitlink modes, Git metadata, malformed/truncated
  diffs, declaration mismatch, and syntactic no-ops.
- Patch application occurs in an adapter-created detached worktree. Git hooks are disabled,
  submodules are not initialized, and cleanup verifies the original checkout state on success and
  failure.
- Candidate tests use a non-root, capability-dropped, no-new-privileges Docker plan with no network,
  read-only roots, PID/CPU/memory/output/time limits, and no Docker socket.
- Evidence excludes prompts, raw responses, patch/source text, gold material, secrets, host identity,
  environment dumps, and local paths. The API key is future environment-only state and is never
  serialized, printed, inspected, hashed, or persisted.
- The pure cost guard reserves uncached worst-case cost before a call, requires provider usage,
  rejects ambiguous reservation state, permits no retry or ninth call, and stops before USD 1.0000.
- Fairness validation permits differences only in graph retrieval, architecture constraints,
  orchestration, and execution-feedback access. No condition receives different model, schema,
  validator, evaluator, sandbox, resources, revision, retry, token, or classification policy.

## Finding fixed in this phase

V2.1 had a proposed cost ceiling but no executable reservation/reconciliation state machine and no
mutation-tested fairness validator. V2.1A adds both as immutable domain behavior with synthetic
boundary tests. It also adds an explicit secret-free preflight job and Environment-gated manual
workflow boundary.

## Residual risk

- PySnooper-2's historical qualification retained the immutable fixed revision and successful fixed
  control but not the fixed checkout Git-tree identity. Reacquiring it would require external
  repository access, which this phase prohibits. Readiness therefore fails closed.
- No new Linux qualification, sandbox execution, external checkout, or provider integration was run.
- Docker and the host kernel remain trusted computing boundaries. Static checks cannot prove future
  runner isolation or provider behavior.
- Prompt injection can influence proposed patch bytes, but cannot expand permissions; semantic
  correctness still depends on isolated evaluation and human review.

## External or human review still required

An authorized external identity-only preflight must reacquire PySnooper-2 at the frozen fixed
revision and record its Git-tree identity without exposing source. Human authorization and GitHub
Environment approval remain mandatory before any future provider call. Reviewers should also verify
the official pricing record on the execution date and confirm the workflow execution implementation;
the prepared workflow deliberately exits before provider invocation while readiness is blocked.
