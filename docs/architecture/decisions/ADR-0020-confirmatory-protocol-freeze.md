# ADR-0020: Confirmatory protocol freeze

Status: Accepted for Phase 12.8.

The confirmatory protocol is a canonical, fingerprinted, versioned artifact. It consolidates existing
RQ/Hypothesis/endpoint proposals and fixes pairing, missingness, tests, multiplicity, retries, resource
limits, and amendment semantics before results. It remains proposed until a human approves its exact
fingerprint. Material changes require a new version and invalidate approval. Readiness is recomputed
from evidence and cannot be manually overridden.
