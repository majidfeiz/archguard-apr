# Integration strategy

```text
ArchGuard Core
├── Python API
├── CLI
├── MCP Server (planned)
├── GitHub Action (planned)
├── Codex Skill/Plugin (planned)
└── Claude Code Plugin (planned)
```

External-agent validation mode: Codex, Claude or another external agent proposes a candidate.
Future ArchGuard application use cases analyze and validate it; orchestration stays external.

Internal multi-agent repair mode: future application services coordinate localization, retrieval,
repair, architecture critique, execution and judging through provider-neutral ports.

These modes must remain separable for controlled experiments. Fix evaluation criteria and budgets;
do not silently add internal critique to external baselines. Adapters translate versioned boundary
requests and call use cases, never duplicate business logic. Authentication, authorization,
cancellation, sandboxing, network restrictions and output limits must precede repair exposure.

Phase 3 exposes snapshot-to-graph construction and structural queries through Python and CLI only.
Graph artifacts are provider-neutral. HTTP graph endpoints and all agent integrations remain future work.

Phase 4 exposes explicit profile compilation and graph conformance through Python and CLI only.
Neutral profile/report schemas are suitable future boundaries. No HTTP evaluation, agent, MCP,
Codex or Claude adapter is implemented. Before/after candidate comparison is reserved for Phase 5;
removed Phase 1 architecture placeholder ports must not be used by future adapters.
Phase 5 remains integration-neutral: repair agents may later consume source-free validation
artifacts, but this phase includes no agent, provider, prompt, MCP, or repair generation. Candidate
code is never executed.

Phase 6 provides provider-neutral query, manifest, bundle and evaluation contracts for later repair
agents. The sole implemented method descriptor is `deterministic-graph-retrieval-v1`. A future
semantic implementation may emit the same generic contracts, but Phase 6 does not fake or implement
that baseline.
