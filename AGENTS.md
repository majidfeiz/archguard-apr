# Contributor instructions

Inspect the repository, hidden files and git status before editing. Preserve user work.
Respect entrypoints → application → domain. Domain and application must remain vendor-neutral;
application imports only domain and the standard library. Keep business logic out of adapters.
Add meaningful behavior tests, validate configuration and maintain deterministic experiments.
Never fabricate citations, datasets, metrics or results. Prevent gold-patch and hidden-answer
leakage. Never commit secrets, model outputs or generated benchmark data. Record seeds,
versions, configurations and provenance. Document architectural decisions in ADRs.
Run all checks in README, review the diff and use scoped conventional commits.
Phase 1 contains no actual repair execution or agent integrations.
