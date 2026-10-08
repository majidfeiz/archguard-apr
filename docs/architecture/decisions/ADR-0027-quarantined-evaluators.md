# ADR 0027: Revision-compatible quarantined evaluators

Status: Accepted for Phase 12.8F.4.

BugsInPy task metadata names tests introduced with the fixed revision. Requiring those physical tests
inside the buggy revision invalidates otherwise official selectors. The runner acquires the immutable
fixed-revision test blob, verifies its reviewed hash, keeps it outside both source trees, and mounts it
read-only over the declared test path for buggy and fixed execution. Generated setup markers are empty
and separately mounted. Evaluator material is excluded from agents, prompts, artifacts and repair input.

Adapter v3 binds separate selector plans, evaluator provenance/type, installation plan, working
directory, framework, quarantine policy and review status. Legacy Batch B adapters retain their v2
schema and fingerprints until independently reviewed.
