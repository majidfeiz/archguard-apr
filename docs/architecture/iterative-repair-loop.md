# Iterative repair loop

The Phase 10 core is provider-neutral and evented. A validated task authorizes bounded context and
candidate generation. Each complete replacement patch is schema-parsed, normalized, hashed and
prechecked before Phase 5 worktree creation. Passing candidates proceed in fixed order through
applicability, snapshot analysis, graph construction, architecture evaluation, Phase 7 sandbox tests,
functional delta and acceptance policy. No model can reorder or skip a gate.

Rejected refinable candidates receive bounded verified feedback. Children always target the original
baseline, name an immutable parent and repeat every gate. Exact normalized duplicates are recorded and
not revalidated. Replay validates the hash-chained state events and invokes no provider, patch, Git or
execution boundary. Candidate rejection is distinct from infrastructure failure, convergence and
budget exhaustion.

## Protected changes and threat model

Git/CI configuration, policy/profile/plan files, environment/secrets, lockfiles, test configuration,
tests unless authorized, Docker security files, generated artifacts and gold/solution paths are
protected by default. Heuristics also reject common skip/xfail, no-op assertion, coverage disabling,
unconditional-success and sandbox-weakening edits. Heuristics reduce risk but can produce false
positives and false negatives; deterministic validation remains mandatory. Prompt-injection defenses
also reduce risk but are not a proof of security.

## Acceptance, ranking and stopping

Default acceptance requires applicability, complete analysis, architecture pass with no new errors,
no regressions or missing required tests, target failures fixed, no timeout/infrastructure failure and
successful cleanup. Ranking considers only accepted evidence: regressions, fixed/persistent failures,
architecture errors, patch/file size, round and stable fingerprint. Provider brand, prose and
confidence are excluded.

Stops are explicit: first accepted success when configured, budgets, round/candidate limits, duplicate
convergence, no refinable candidate, cancellation, infrastructure policy or human review. Selected
tests cannot establish complete correctness.

## Lineage and human review

The canonical lineage DAG rejects missing/cross-run parents, cycles and unordered identities, records
duplicates and selected node, and is reconstructible from events. Human approval must bind the exact
run, candidate/evidence/checkpoint fingerprints and never bypasses validation; stale decisions fail.
