# Anthropic Messages adapter

The adapter calls typed Messages with one forced `submit_agent_response` tool. Its strict input schema
is derived from provider-neutral `AgentResponse`. Unexpected or conflicting tools, malformed inputs,
empty content, refusals and output-limit stop reasons fail closed. No provider/server tool is enabled.
Returned model, public request ID and reported token/cache/thinking usage are translated. Actual models
depend on Anthropic account access.
