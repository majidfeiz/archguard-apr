# Repair CLI

`archguard repair task validate --task TASK` validates task policy without repository/provider access.
`task inspect` emits a source-free summary. Existing run status/replay and human-decision commands stay
available. Outputs are stable JSON, immutable destinations refuse overwrite, and provider keys are
never CLI options. Live execution remains governed by Phase 9 credential and cost acknowledgements.
