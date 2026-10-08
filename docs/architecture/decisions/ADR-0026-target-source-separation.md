# ADR 0026: Separate target source from evaluator images

Status: Accepted for Phase 12.8F.3.

Evaluator images contain dependencies only. Exact buggy and fixed checkouts are acquired and verified
independently, mounted read-only at `/workspace`, and checked from inside the container before test
execution. The image build-context hash and image ID detect stale or substituted images; host and
container working-tree hashes detect stale or substituted mounts.

Buggy execution declares `TEST_FAILURE`; fixed execution declares `EXIT_ZERO`. Result normalization
receives this expectation explicitly, and fixed evidence rejects `EXPECTED_FAILURE`. This keeps shared
dependencies while preventing target-source or outcome semantics from being shared accidentally.
