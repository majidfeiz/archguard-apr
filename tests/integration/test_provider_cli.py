import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from archguard.domain.orchestration import AgentRole
from archguard.entrypoints.cli.app import app

pytestmark = pytest.mark.integration
runner = CliRunner()


@pytest.fixture
def provider_config(tmp_path: Path) -> Path:
    roles = {
        role.value: "openai"
        for role in AgentRole
        if role not in {AgentRole.COORDINATOR, AgentRole.HUMAN_GATE}
    }
    path = tmp_path / "providers.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "archguard.provider-config/v1",
                "providers": [
                    {
                        "provider": "openai",
                        "model": "test-model",
                        "structured_output_mode": "strict_json_schema",
                        "model_allowlist": ["test-model"],
                    }
                ],
                "role_to_provider": roles,
            }
        )
    )
    return path


def test_provider_cli_is_offline(provider_config: Path) -> None:
    validate = runner.invoke(
        app, ["provider", "config", "validate", "--config", str(provider_config)]
    )
    assert validate.exit_code == 0
    assert json.loads(validate.stdout)["status"] == "valid"
    listed = runner.invoke(app, ["provider", "list", "--config", str(provider_config)])
    assert json.loads(listed.stdout)["providers"][0]["model"] == "test-model"
    capabilities = runner.invoke(
        app, ["provider", "capabilities", "--provider", "openai", "--config", str(provider_config)]
    )
    assert "strict_json_schema" in json.loads(capabilities.stdout)["capabilities"]
    doctor = runner.invoke(
        app, ["provider", "doctor", "--provider", "openai", "--config", str(provider_config)]
    )
    assert doctor.exit_code == 1
    assert json.loads(doctor.stdout)["network_request"] is False


def test_provider_cli_rejects_live_without_ack(provider_config: Path) -> None:
    result = runner.invoke(
        app, ["provider", "smoke-test", "--provider", "openai", "--config", str(provider_config)]
    )
    assert result.exit_code == 2
    assert "live_execution_not_acknowledged" in result.stdout


def test_provider_cli_rejects_invalid(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("api_key: recognizable-fake-secret\n")
    result = runner.invoke(app, ["provider", "config", "validate", "--config", str(path)])
    assert result.exit_code == 2
    assert "recognizable-fake-secret" not in result.stdout
