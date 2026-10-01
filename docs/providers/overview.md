# Provider integration

Phase 9 connects the Phase 8 `AgentPort` boundary to OpenAI Responses and Anthropic Messages through
replaceable infrastructure adapters. Domain and application code contain no provider SDK imports.
Coordinator and HumanGate remain application-controlled. Capability negotiation fails before a paid
request; structured output never silently falls back to prose.

Configuration uses `archguard.provider-config/v1`; see `configs/providers.example.yaml`. Model names
come from `OPENAI_MODEL` and `ANTHROPIC_MODEL`, and credentials only from `OPENAI_API_KEY` and
`ANTHROPIC_API_KEY`. API access is separate from consumer subscriptions and may incur costs.
`archguard repair run start --providers providers.yaml` validates provider policy before creating a
run; subsequent orchestration invokes adapters only through the typed application port.

Three concepts are distinct: prompt construction and parsing/validation are deterministic; provider
inference is not. Replay consumes recorded validated `AgentResponse` values and performs no provider
call. Structured output guarantees shape, not correctness. Phase 5 and Phase 7 gates remain mandatory.
