# OpenAI Responses adapter

The adapter calls `client.responses.create`, supplies strict `text.format` JSON Schema, sets no tools,
and uses configured model/output/timeout controls. It handles refusal content, incomplete status,
output limits, empty/multiple text items, returned model, request ID and reported usage. Normalized
errors never expose raw bodies. Stateless policy sends `store=false`; this is not a zero-retention
guarantee. Actual models depend on OpenAI account/project access.
