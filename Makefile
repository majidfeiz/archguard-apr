.PHONY: install format lint typecheck test test-cov check run doctor docker-build docker-up docker-down

install:
	uv sync --frozen

format:
	uv run ruff format .

lint:
	uv run ruff check .

typecheck:
	uv run mypy src tests

test:
	uv run pytest

test-cov:
	uv run pytest --cov-report=html

check:
	uv lock --check
	uv run ruff format --check .
	uv run ruff check .
	uv run mypy src tests
	uv run pytest

run:
	uv run uvicorn archguard.entrypoints.api.app:create_app --factory --host 127.0.0.1

doctor:
	uv run archguard doctor

docker-build:
	docker build -t archguard-apr:phase-4 .

docker-up:
	docker compose up --build

docker-down:
	docker compose down

.PHONY: graph-smoke graph-benchmark
graph-smoke:
	uv run archguard repository analyze examples/python/simple-layered-app --source-root src --output /tmp/archguard-snapshot.json
	uv run archguard graph build /tmp/archguard-snapshot.json --output /tmp/archguard-graph.json
	uv run archguard graph inspect /tmp/archguard-graph.json
	uv run archguard graph cycles /tmp/archguard-graph.json

graph-benchmark:
	uv run python scripts/benchmark_repository_graph.py

.PHONY: architecture-smoke architecture-self architecture-benchmark context-self
architecture-smoke: graph-smoke
	uv run archguard architecture profile validate examples/architecture/simple-layered.yaml
	uv run archguard architecture profile compile examples/architecture/simple-layered.yaml --output /tmp/archguard-profile.json
	uv run archguard architecture evaluate /tmp/archguard-graph.json --profile examples/architecture/simple-layered.yaml --output /tmp/archguard-report.json
	uv run archguard architecture inspect /tmp/archguard-report.json

architecture-self:
	uv run archguard repository analyze . --config configs/architecture-self.yaml --output /tmp/archguard-self-snapshot.json
	uv run archguard graph build /tmp/archguard-self-snapshot.json --output /tmp/archguard-self-graph.json --protected-root .
	uv run archguard architecture evaluate /tmp/archguard-self-graph.json --profile .archguard/architecture.yaml --output /tmp/archguard-self-report.json --protected-root .

context-self:
	uv run python scripts/context_self_check.py

architecture-benchmark:
	uv run python scripts/benchmark_constraint_engine.py
