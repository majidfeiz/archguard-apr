# Execution plan v1

`archguard.execution-plan/v1` is a trusted, immutable validation-plan contract. Plans contain an
ordered list of argument vectors; command strings and shells are not supported. Each stage declares
a repository-relative working directory, bounded timeout, result adapter, expected artifacts and
stop/continue policy. The plan declares a total timeout, CPU, memory, PID, `/tmp` and captured-output
limits. Environment inheritance is empty by default: callers may supply only named allowlisted
values, while controlled constants are stored in the plan.

Images must use `name@sha256:<64 lowercase hex>` or the immutable local image identity
`sha256:<64 lowercase hex>`. Tags are rejected. `.` means the repository root; absolute paths,
parent traversal, backslashes, NULs, duplicate stage IDs and unsupported schemas are rejected.
Canonical JSON uses sorted keys, compact UTF-8 and a terminal newline.

[`examples/execution/archguard-self.yaml`](../../examples/execution/archguard-self.yaml) is safe to
validate. Its zero digest is deliberately non-runnable documentation: replace it with the inspected
ID of a locally built, trusted `Dockerfile.validation` image before execution.
