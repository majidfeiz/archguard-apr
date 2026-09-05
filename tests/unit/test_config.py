from pathlib import Path

import pytest

from archguard.infrastructure.config import Settings, load_settings, read_yaml
from archguard.infrastructure.paths import writable_directory

pytestmark = pytest.mark.unit


def test_defaults() -> None:
    settings = Settings()
    assert settings.execution_timeout == 300
    assert settings.random_seed == 0
    assert settings.repair_provider is None
    assert not settings.provider_execution_enabled


def test_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "app.yaml"
    config.write_text("execution_timeout: 20\nrandom_seed: 7\n")
    assert load_settings(config).execution_timeout == 20
    assert load_settings(config).random_seed == 7
    (tmp_path / ".env").write_text("ARCHGUARD_EXECUTION_TIMEOUT=30\n")
    assert load_settings(config).execution_timeout == 30
    monkeypatch.setenv("ARCHGUARD_EXECUTION_TIMEOUT", "40")
    assert load_settings(config).execution_timeout == 40


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "invalid"])
def test_invalid_timeout(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("ARCHGUARD_EXECUTION_TIMEOUT", value)
    with pytest.raises(ValueError):
        Settings()


@pytest.mark.parametrize("content", ["[]", "- one", "42", "a: [", "1: value", "unknown: value"])
def test_invalid_yaml(tmp_path: Path, content: str) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text(content)
    with pytest.raises(ValueError):
        load_settings(path)


def test_provider_disabled_and_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARCHGUARD_PROVIDER_EXECUTION_ENABLED", "true")
    with pytest.raises(ValueError):
        Settings()
    monkeypatch.delenv("ARCHGUARD_PROVIDER_EXECUTION_ENABLED")
    monkeypatch.setenv("ARCHGUARD_REPAIR_MODEL", " ")
    with pytest.raises(ValueError):
        Settings()
    monkeypatch.setenv("ARCHGUARD_REPAIR_MODEL", "research-model")
    assert Settings().repair_model == "research-model"


def test_missing_config(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        read_yaml(tmp_path / "missing")


def test_writability(tmp_path: Path) -> None:
    assert writable_directory(tmp_path / "not-created" / "nested")
    assert not (tmp_path / "not-created").exists()
    file = tmp_path / "file"
    file.touch()
    assert not writable_directory(file)
