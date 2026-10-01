# Deterministic prompt construction

Phase 8 LLM roles share a versioned, stable section order: protocol, role, task, allowed/prohibited
actions, policy, remaining budget, artifact references, mandatory validation, response schema and
delimited untrusted data. Coordinator and HumanGate cannot be prompted. The template fingerprint
excludes untrusted content. Prompts request concise assumptions/evidence, never private chain-of-thought.
