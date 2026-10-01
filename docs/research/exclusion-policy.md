# Exclusion policy

Exclusions use the versioned reason enum: unsupported language/platform, missing license/source/
revision/dependency, build/analysis/graph/evaluator failure, external service, resource limit,
nondeterminism, missing target failure, gold-isolation failure, or preregistered policy exclusion.
Records remain in manifests with all applicable reasons. Failed and unavailable observations are not
relabelled as repair failures. Policy changes require a new manifest version and written rationale.
