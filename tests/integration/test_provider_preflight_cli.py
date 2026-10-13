import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from archguard.entrypoints.cli.app import app

pytestmark = pytest.mark.integration
runner = CliRunner()


def test_provider_preflight_is_offline_and_requires_key(
    repository_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = runner.invoke(
        app,
        [
            "experiment",
            "provider-preflight",
            "--config",
            str(repository_root / "configs/experiments/phase13-provider.json"),
            "--output-directory",
            str(repository_root.parent / "phase13-output"),
        ],
    )
    assert result.exit_code == 4
    report = json.loads(result.stdout)
    assert report["mode"] == "offline"
    assert report["network_request"] is False
    assert report["checks"]["secret_present"] is False


def test_live_preflight_requires_both_flags(repository_root: Path) -> None:
    result = runner.invoke(
        app,
        [
            "experiment",
            "provider-preflight",
            "--config",
            str(repository_root / "configs/experiments/phase13-provider.json"),
            "--live",
        ],
    )
    assert result.exit_code == 5
    assert "requires_both" in result.stdout
