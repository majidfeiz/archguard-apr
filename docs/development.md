# Development

Use Python 3.12 and `uv sync --frozen`. Run `make check`, `uv build`, CLI smoke commands,
`docker compose config` and Docker build. CI checks both supported Python minor versions.
Use pre-commit. `uv lock --check` verifies consistency; review intentional `uv lock` updates.

Configuration: environment > current-directory .env > explicit YAML/constructor > defaults.
Loading creates no directories. Doctor probes the nearest existing output parent with a temporary
file; this does not guarantee future writes or isolation.

Call `configure_logging` explicitly. It configures the ArchGuard logger without changing root
handlers. Pass `extra={"experiment_id": ..., "run_id": ...}` for context. UTC logs redact labeled
tokens, keys, secrets, passwords and authorization values including exceptions. This cannot detect
arbitrary bare credentials: never log provider payloads or secrets directly.

Canonical experiment JSON has sorted keys; array order is preserved. Domain timestamps normalize
to UTC; boundary TypeAdapters can serialize immutable dataclasses. Relative paths reject Windows
and POSIX traversal but do not sandbox symlinks. No untrusted-code runner exists.
AST tests resolve relative imports and forbid dynamic core loading. Ruff uses E/F/I/UP/B.

One narrow mypy suppression tests the frozen-dataclass runtime mutation guard; production code
has no type-check suppression.
