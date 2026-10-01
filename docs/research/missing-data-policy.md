# Missing-data and failure policy

Every attempt is retained. Provider refusal/rate limit/outage/authentication, malformed output, timeout,
build failure, nondeterminism, evaluator/setup failure, budget exhaustion and cancellation have distinct
codes. Do not retry silently. Separate system failure, task exclusion, unresolved repair, missing
observation and infrastructure failure. Intention-to-run summaries retain every scheduled denominator;
valid-run sensitivity summaries exclude unavailable outcomes but report exclusions. Infrastructure
failure is never success, and unresolved repair is never an infrastructure observation.
