# ADR-0022: Bounded external evidence acquisition

Status: Accepted for Phase 12.8B.

## Context

Phase 12.8A could identify missing license and architecture evidence but deliberately could not acquire
external source. Evidence generation must inspect a pinned buggy tree without allowing mutable identity,
target execution, fixed/gold influence, host-path leakage, or unbounded network and disk use.

## Decision

A narrow infrastructure adapter acquires only an explicit allowlist of full Git commit identities from
official HTTPS remotes. Hooks, recursive submodules, LFS payloads, escaping symlinks, and gitlinks are
rejected. Buggy, fixed, framework metadata, transient graph artifacts, and uploaded evidence use distinct
temporary directories outside the project. Only the buggy tree enters the existing read-only repository
analysis and graph pipeline. Two independent graph runs must produce byte-identical source-free summaries.

The uploaded transport has an exact flat allowlist, canonical JSON, complete checksums, strict validation,
and no source, patch, gold, raw log, environment dump, or credential material. License uncertainty is a
valid `UNRESOLVED` result. It remains a readiness blocker but does not invalidate successful engineering
execution. Human review records are never changed automatically.

## Consequences

External execution is intentionally restricted to a manual Linux x86_64 workflow with a 250 MiB ceiling
and cleanup before upload. The fixed revision is identity-checked but cannot influence architecture
evidence. A validated artifact can update only facts it directly supports; `phase_13_ready` remains false.
