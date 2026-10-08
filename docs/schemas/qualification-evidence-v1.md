# Qualification evidence v1

`archguard.qualification-evidence/v1` contains canonical task results. Each result binds the adapter
and exact revisions, three source-free buggy attempts, fixed-control status, classification,
qualification decision, base-image identity, dependency artifact filenames/hashes, prior-evidence
status, and resource ceilings. Attempts contain only exit code, test counts, normalized
category/signature hash, bounded duration, and truncation status. Infrastructure failures additionally
record a stage/code, return code, normalized error class and stderr hash, command category and
retryability without raw logs. Their scientific classification remains unresolved.

Phase 12.8F.2 requires the full structured fixed-control record documented in
`fixed-control-evidence-v1.md`. Fixed and buggy dependency-environment fingerprints must match. A failed
fixed test is `FIXED_CONTROL_FAILED`; fixed infrastructure failure is
`FIXED_CONTROL_INFRASTRUCTURE_FAILURE`. Neither is automatically `ENVIRONMENT_SENSITIVE`.

The flat Artifact contains exactly ten allowlisted files documented in the Phase 12.8F verification
guide. Validation rejects replacement tasks, registry/policy mismatch, abbreviated revisions,
duplicates, classification contradictions, STABLE without a passing fixed control, prior conflicts
marked qualified, source/gold/raw-log fields, unsafe ZIPs, hash errors, and incomplete cleanup or
security evidence. Import is byte-idempotent and rejects contradictory existing output.

Phase 12.8F.3 adds the explicit `EXIT_ZERO` expectation, framework and installation mode, collection
count, selected-test fingerprint, and independent source identity. Source identity contains only
revision/tree/build/working-directory fingerprints. New evidence rejects fixed `EXPECTED_FAILURE`,
identical buggy/fixed Git trees, target source in the image, and host/container tree mismatch.
Historical v1 artifacts remain unchanged.
