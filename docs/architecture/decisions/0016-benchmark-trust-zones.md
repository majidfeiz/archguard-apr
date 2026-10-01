# ADR 0016: Separate benchmark trust zones

Status: accepted for Phase 11.

Benchmark metadata is immutable domain data; deterministic policy lives in application services;
YAML/cache handling and future benchmark adapters remain infrastructure. A dedicated trusted evaluator
port is separate from agent ports. Agent, evaluator and gold zones use separate paths and only
source-free evidence or hashes cross toward the agent. This makes leakage fail closed and permits
offline fixtures, at the cost of explicit acquisition/evaluation adapters and duplicated storage.
