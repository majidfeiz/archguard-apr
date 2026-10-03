# Phase 12.8A research-evidence schemas

- `archguard.license-evidence/v1` separates framework, dataset, and project scope; binds evidence to a
  full Git revision and optional license-file SHA-256; and permits only VERIFIED, UNRESOLVED, INELIGIBLE.
- `archguard.architecture-graph-evidence/v1` binds source-free graph facts to exact revision and profile
  fingerprint. VALIDATED requires complete counts and zero ambiguous/unassigned modules.
- `archguard.candidate-registry/v1` records outcome-blind metadata, exclusions, deterministic ordering,
  and project-stratified pilot selection.
- `archguard.qualification-pilot-plan/v1` records an immutable source-free task list and isolation/resource
  limits. It cannot represent final-population freeze.
- `archguard.power-design-analysis/v1` records prospective assumptions and deterministic exact paired
  binary power scenarios without using repair outcomes.
