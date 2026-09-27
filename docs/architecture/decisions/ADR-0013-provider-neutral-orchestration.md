# ADR-0013: Provider-neutral event-sourced repair orchestration

Status: accepted

Phase 8 represents agents as a narrow typed port and treats every response as untrusted data. A
single application coordinator owns transitions, budgets, candidate registration, evidence-based
ranking, checkpoints and human decisions. Canonical hash-chained events support deterministic replay
and verified resume without repeating effects.

Provider SDK objects, prompts, callbacks, shell commands, direct Git/Docker access and agent-claimed
validation are excluded. Scripted agents prove semantics before Phase 9 provider adapters. Hash
chains establish tamper evidence, not authorship, and deterministic scripted orchestration does not
imply deterministic future providers.
