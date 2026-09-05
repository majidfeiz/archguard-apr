# ADR-0004: Canonical repository graph

Status: Accepted for Phase 3 implementation; pending pull-request review.

## Context

RepositorySnapshot v1 supplies immutable syntax facts. Research needs reproducible structural
relationships independently of source scanning, execution, graph libraries and later inference.

## Decision

Use a separate graph schema `"1"` with frozen domain dataclasses and directed multigraph edges.
Reuse symbol IDs; digest canonically framed edge metadata with occurrence ranks. Store sorted
records and an identity fingerprint; validate typed metadata and graph-wide invariants on creation
and read. Separate builder, artifact reader/writer and query services through neutral ports.

Omit redundant `declares`. Omit ambiguous module nodes, preserve files/symbols and retain unresolved
imports in typed diagnostics. Resolve exact submodule then base module only; preserve external syntax
prefixes without distribution claims. Relative failures never become external dependencies.
Include TYPE_CHECKING occurrences and provide filtered cycle queries. No NetworkX is required.

## Consequences

Artifacts are portable and independently queryable, with no source reads during graph construction.
Conservative resolution can be incomplete; partial status is explicit. Persistence shares canonical
JSON and safe byte I/O with snapshots. Sorting and validation cost memory/time; a bounded engineering
script tracks scale without claiming research results. Later adapters can convert these values to
other graph formats without redefining the research artifact. Architecture compliance remains future work.
