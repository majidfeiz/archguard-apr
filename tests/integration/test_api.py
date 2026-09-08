from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from archguard.entrypoints.api.app import create_app
from archguard.infrastructure.config import Settings

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/health", {"status": "ok"}),
        ("/ready", {"status": "ready"}),
        ("/version", {"version": "0.6.0"}),
    ],
)
def test_endpoints(path: str, expected: dict[str, str]) -> None:
    with TestClient(create_app()) as client:
        response = client.get(path)
        assert response.status_code == 200
        assert response.json() == expected


def test_factory_isolation(tmp_path: Path) -> None:
    first = create_app(Settings(workspace_dir=tmp_path / "first"))
    second = create_app(Settings(workspace_dir=tmp_path / "second"))
    assert first.state.settings.workspace_dir != second.state.settings.workspace_dir
    first.state.settings.random_seed = 7
    assert second.state.settings.random_seed == 0


def test_invalid_config_fails_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARCHGUARD_EXECUTION_TIMEOUT", "0")
    with pytest.raises(ValueError):
        create_app()
