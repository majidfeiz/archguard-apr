# Qualification evidence v1

`archguard.qualification-evidence/v1` contains canonical task results. Each result binds the adapter
and exact revisions, three source-free buggy attempts, fixed-control status, classification,
qualification decision, base-image identity, dependency artifact filenames/hashes, prior-evidence
status, and resource ceilings. Attempts contain only exit code, test counts, normalized
category/signature hash, bounded duration, and truncation status. Infrastructure failures additionally
record a stage/code, return code, normalized error class and stderr hash, command category and
retryability without raw logs. Their scientific classification remains unresolved.

The flat Artifact contains exactly ten allowlisted files documented in the Phase 12.8F verification
guide. Validation rejects replacement tasks, registry/policy mismatch, abbreviated revisions,
duplicates, classification contradictions, STABLE without a passing fixed control, prior conflicts
marked qualified, source/gold/raw-log fields, unsafe ZIPs, hash errors, and incomplete cleanup or
security evidence. Import is byte-idempotent and rejects contradictory existing output.
