# Phase 12.8F.2 fixed-control diagnostics

Baseline is clean local `main` at `351d6e93064a7d6d597bb837b64ce06d62a5045c`, version `0.12.8`.
Phase 12.8F.1 repaired infrastructure execution. Run `37672954475` then executed all four Batch A tasks:
three infrastructure-valid buggy repetitions had stable failure signatures for each task, while every
fixed control failed and zero tasks qualified. Its source-free Artifact does not identify the fixed
failure stages, so no task-specific cause is proven. The run is preserved as diagnostic historical
evidence and is not imported as qualified evidence.

No revision, selector, dependency declaration, candidate, adapter fingerprint or task identity changes
in this phase. The workflow is narrowed to Batch A and records structured fixed-control evidence. Failed
controls are `FIXED_CONTROL_FAILED` or `FIXED_CONTROL_INFRASTRUCTURE_FAILURE`, never automatically
`ENVIRONMENT_SENSITIVE`; scientific classification remains unresolved and review is required.

Run the diagnostic workflow after merge:

```bash
gh workflow run phase-12-8f-linux-x86-qualification.yml --ref main -f task_id=batch-a
```

Expected Artifact name is
`archguard-phase-12-8f-qualification-batch-a-<run-id>`. The existing package, validate and import tools
remain applicable, but a diagnostic run must not be imported as qualification unless its validated
results are genuinely qualified. Batch B is unavailable from this workflow. No local benchmark,
provider, repair, Batch B or Phase 13 execution occurred. `phase_13_ready=false`.
