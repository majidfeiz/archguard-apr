# ADR-0001: Agent-agnostic core

Status: Accepted.

Context: Provider coupling would confound experiments and duplicate validation logic.
Decision: Use a ports-and-adapters modular monolith, frozen standard-library domain values and
application Protocols. Artifact references defer detailed graph and patch design.
Consequences: Adapters own frameworks and explicit wiring. Static dependency tests guard the core.
External validation and internal orchestration remain separate experimental conditions.
