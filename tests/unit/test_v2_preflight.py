import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from archguard.domain.v2_preflight import PreflightBlocker, evaluate_preflight
from archguard.entrypoints.cli.app import app
from archguard.infrastructure.v2_preflight import load_v2_preflight_manifest

pytestmark = pytest.mark.unit
runner = CliRunner()


def test_ready_preflight_is_canonical_deterministic_and_offline(
    repository_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = repository_root / "examples/v2/preflight-ready.json"
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    outputs = [tmp_path / "first.json", tmp_path / "second.json"]
    for output in outputs:
        result = runner.invoke(
            app,
            ["experiment", "v2", "preflight", "--manifest", str(manifest), "--output", str(output)],
        )
        assert result.exit_code == 0, result.output
        summary = json.loads(result.stdout)
        assert summary["status"] == "READY"
        assert summary["provider_calls_executed"] == 0
        assert summary["source_bearing_output"] is False
    assert outputs[0].read_bytes() == outputs[1].read_bytes()
    assert outputs[0].read_bytes().endswith(b"\n")
    assert str(repository_root).encode() not in outputs[0].read_bytes()


def test_blocked_preflight_reports_stable_codes(repository_root: Path, tmp_path: Path) -> None:
    source = json.loads((repository_root / "examples/v2/preflight-ready.json").read_text())
    source["checks"]["license_eligible"] = False
    source["checks"]["gold_absent"] = False
    manifest = tmp_path / "blocked.json"
    manifest.write_text(json.dumps(source))
    output = tmp_path / "result.json"
    result = runner.invoke(
        app,
        ["experiment", "v2", "preflight", "--manifest", str(manifest), "--output", str(output)],
    )
    assert result.exit_code == 3
    value = json.loads(output.read_text())
    assert value["blocker_codes"] == [
        PreflightBlocker.GOLD_LEAKAGE_DETECTED,
        PreflightBlocker.LICENSE_INELIGIBLE,
    ]


def test_unknown_missing_duplicate_and_existing_outputs_fail_closed(
    repository_root: Path, tmp_path: Path
) -> None:
    original = json.loads((repository_root / "examples/v2/preflight-ready.json").read_text())
    for index, changed in enumerate(
        (
            {**original, "unknown": True},
            {key: value for key, value in original.items() if key != "task_id"},
        )
    ):
        manifest = tmp_path / f"invalid-{index}.json"
        manifest.write_text(json.dumps(changed))
        result = runner.invoke(
            app,
            [
                "experiment",
                "v2",
                "preflight",
                "--manifest",
                str(manifest),
                "--output",
                str(tmp_path / f"out-{index}.json"),
            ],
        )
        assert result.exit_code == 2
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"schema":"x","schema":"y"}')
    with pytest.raises(ValueError):
        load_v2_preflight_manifest(duplicate)
    existing = tmp_path / "existing.json"
    existing.write_text("preserve")
    result = runner.invoke(
        app,
        [
            "experiment",
            "v2",
            "preflight",
            "--manifest",
            str(repository_root / "examples/v2/preflight-ready.json"),
            "--output",
            str(existing),
        ],
    )
    assert result.exit_code == 4 and existing.read_text() == "preserve"


def test_invalid_resource_ceiling_is_a_blocker(repository_root: Path) -> None:
    manifest = load_v2_preflight_manifest(repository_root / "examples/v2/preflight-ready.json")
    object.__setattr__(manifest, "cpu_limit", 0)
    result = evaluate_preflight(manifest)
    assert result.status == "BLOCKED"
    assert result.blocker_codes == (PreflightBlocker.RESOURCE_CEILINGS_INVALID,)
