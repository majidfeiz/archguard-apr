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
	docker build -t archguard-apr:phase-2 .

docker-up:
	docker compose up --build

docker-down:
	docker compose down
