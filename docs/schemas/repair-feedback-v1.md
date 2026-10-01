# Repair feedback v1

`archguard.repair-feedback/v1` contains a candidate/stage reference, sorted rejection categories and
test identifiers, a source-free excerpt bounded to 4096 bytes, remaining budgets and allowlisted next
actions. It excludes raw logs, secrets, host paths, container IDs, source files, gold patches and model
reasoning. Sensitive feedback bundles require a separate explicit policy and are not produced by the
normal artifact writer.
