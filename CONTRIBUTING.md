# Contributing

Read [AGENTS.md](AGENTS.md) and [the development guide](docs/development.md). Open an issue before a
large change. Describe reproducible behavior or a falsifiable research task, preserve architectural
boundaries, add meaningful tests, and use a scoped conventional commit.

```bash
uv sync --frozen
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
```

Research contributions must record provenance, versions, seeds, configuration, exclusions, and
negative results. Never submit credentials, raw provider payloads, benchmark source, restricted
datasets, evaluator-only assets, gold/reference patches, generated model outputs, or unsupported
performance claims. Documentation and data contributions must have compatible licensing and clear
attribution. Architecture decisions belong in ADRs. By contributing, you agree to follow the
[Code of Conduct](CODE_OF_CONDUCT.md) and the applicable repository licenses.
