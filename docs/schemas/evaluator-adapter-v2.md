# Evaluator adapter v2

`archguard.evaluator-adapter/v2` binds one selected task to its official repository, full buggy and
fixed revisions, Python version, immutable requirements-file locator/hash/empty state, exact dependency
constraints with their own canonical fingerprint and reviewed provenance, structured evaluator argv,
exact selector, expected buggy outcome, fixed-control condition, source-license identity, and sandbox
contract. Its fingerprint is SHA-256 over canonical JSON without the fingerprint field.

Version 2 canonically migrates repository-controlled v1 entry-point strings to allowlisted argv arrays.
Task revisions, selectors, membership and ordering are unchanged; v1 remains historical evidence only.

The common sandbox permits at most 2 CPUs, 2 GiB RAM, 256 PIDs, 20 minutes, 1 MiB combined output and
a 256 MiB tmpfs. Evaluation requires network none, non-root identity, read-only root and source,
dropped capabilities, no-new-privileges, and no Docker socket. PySnooper-2 has no new adapter because
its imported Linux x86 evidence remains authoritative.
