from pathlib import Path

import yaml


def test_workflow_inputs_batches_and_runner_temp(repository_root: Path) -> None:
    path = repository_root / ".github/workflows/phase-12-8f-linux-x86-qualification.yml"
    raw = path.read_text()
    workflow = yaml.safe_load(raw)
    dispatch = workflow[True]["workflow_dispatch"]
    assert dispatch["inputs"]["task_id"]["default"] == "batch-a"
    assert set(dispatch["inputs"]["task_id"]["options"]) == {
        "batch-a",
        "batch-b",
        "PySnooper-1",
        "PySnooper-3",
        "black-1",
        "cookiecutter-4",
        "black-2",
        "black-3",
        "black-4",
        "all",
    }
    assert workflow["permissions"] == {"contents": "read"}
    assert "runs-on: ubuntu-24.04" in raw
    assert "max-parallel: 1" in raw and "fail-fast: false" in raw
    assert "${{ runner.temp }}" not in raw and "${RUNNER_TEMP}" in raw
    assert 'mkdir -p "${evidence_root}"' not in raw


def test_workflow_sandbox_cleanup_and_single_artifact(repository_root: Path) -> None:
    raw = (
        repository_root / ".github/workflows/phase-12-8f-linux-x86-qualification.yml"
    ).read_text()
    assert raw.count("uses: actions/upload-artifact@v7") == 1
    assert "retention-days: 14" in raw
    assert "if: always()" in raw
    assert "name: Enforce transfer, disk, leakage, and cleanup gates\n        if: always()" in raw
    assert "--network" in (repository_root / "scripts/phase128f_runner.py").read_text()
    for text in (
        "--read-only",
        "--cap-drop",
        "no-new-privileges:true",
        "--pids-limit",
        "--memory",
        "--cpus",
        "--user",
    ):
        assert text in (repository_root / "scripts/phase128f_runner.py").read_text()
    assert "2147483648" in raw and "8589934592" in raw and "10485760" in raw
