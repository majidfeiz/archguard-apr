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
