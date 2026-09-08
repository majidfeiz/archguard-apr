# ADR-0011: Separate source-free manifests from sensitive bundles

Status: accepted.

Retrieval manifests contain hashes, safe relative identifiers, scores, graph evidence and budget
decisions but no raw problem, traceback, error, or source text. Context bundles are separately
versioned, marked `sensitive-source-bearing`, require explicit CLI acknowledgement, and contain only
snapshot-bound selected ranges. Normal CLI output and inspection expose bundle metadata only.
