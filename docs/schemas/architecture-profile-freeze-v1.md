# Architecture profile freeze v1

`archguard.architecture-profile-freeze/v1` is a canonical, fingerprinted record binding one task and
one compiled profile fingerprint to an approval decision SHA-256 and imported evidence fingerprint.
Its status must be `FROZEN`, while `phase_13_ready` remains false.

Validation recompiles the referenced YAML profile and requires the compiled fingerprint to equal the
frozen fingerprint. It also validates the complete imported Phase 12.8C evidence and hashes the exact
approval record. Profile drift, approval mutation, evidence replacement, or cross-task reuse fails
closed. The record freezes only the named profile and conveys no protocol or benchmark approval.
