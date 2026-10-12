from pathlib import Path

import yaml

from scripts.phase128f_job_summary import render
from scripts.phase128f_registry import registry


def test_workflow_inputs_batches_and_runner_temp(repository_root: Path) -> None:
    path = repository_root / ".github/workflows/phase-12-8f-linux-x86-qualification.yml"
    raw = path.read_text()
    workflow = yaml.safe_load(raw)
    assert workflow["name"] == "Phase 12 Final Black Qualification"
    dispatch = workflow[True]["workflow_dispatch"]
    assert dispatch == {}
    assert workflow["permissions"] == {"contents": "read"}
    assert "runs-on: ubuntu-24.04" in raw
    assert "max-parallel: 1" in raw and "fail-fast: false" in raw
    assert "${{ runner.temp }}" not in raw and "${RUNNER_TEMP}" in raw
    assert 'mkdir -p "${evidence_root}"' not in raw
    registry_fingerprint = registry()["fingerprint"]
    assert isinstance(registry_fingerprint, str)
    assert registry_fingerprint in raw


def test_workflow_sandbox_cleanup_and_single_artifact(repository_root: Path) -> None:
    raw = (
        repository_root / ".github/workflows/phase-12-8f-linux-x86-qualification.yml"
    ).read_text()
    assert raw.count("uses: actions/upload-artifact@v7") == 1
    assert "- name: Upload one source-free qualification Artifact\n        if: always()" in raw
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
    assert "phase128f_security_scan.py" in raw
    assert '--output "${SECURITY_SCAN_PATH}" || gate_failed=1' in raw
    assert "rg -n" not in raw
    assert "phase128f_job_summary.py" in raw
    runner = (repository_root / "scripts/phase128f_runner.py").read_text()
    assert '"pull", "--platform", "linux/amd64"' in runner
    assert "FINAL_BLACK_TASKS = BATCH_B" in runner
    assert "owned-base-reference.txt" in raw and "label=archguard.phase=12.8f" in raw
    assert "--selection final-black" in raw and "--runtime-canary" not in raw
    assert "--collection-diagnostic" not in raw
    assert "--selection PySnooper-1" not in raw
    for task_id in ("black-2", "black-3", "black-4"):
        assert task_id in raw
    assert "--input research/evaluators/adapter-registry-v2.json" in raw
    assert "adapter-registry-v3.json" not in raw
    assert raw.count("--input") == 2
    assert '--input "${RESULTS_PATH}"' in raw
    assert "archguard-phase-12-final-black-qualification-${GITHUB_RUN_ID}" in raw


def test_summary_uses_recorded_fixed_stage_and_category() -> None:
    summary = render(
        "batch-a",
        [
            {
                "task_id": "PySnooper-1",
                "buggy_result_status": "BUGGY_RESULT",
                "fixed_control_passed": False,
                "fixed_control": {
                    "outcome": "OTHER_FAILURE",
                    "stage": "TEST_COLLECTION",
                    "normalized_failure_class": "COLLECTION_ERROR",
                    "source_identity": {
                        "working_directory_fingerprint": "a",
                        "container_visible_source_fingerprint": "a",
                    },
                },
                "qualification_decision": "NOT_QUALIFIED",
            }
        ],
        "PASSED",
    )
    assert "Fixture acquired" in summary and "Source mounted" in summary
    assert summary.startswith("## Phase 12 Final Black Qualification")
    assert "Project import" in summary and "NOT_QUALIFIED" in summary
    assert "Evaluator loaded by pytest" in summary and "Resolved selector" in summary
