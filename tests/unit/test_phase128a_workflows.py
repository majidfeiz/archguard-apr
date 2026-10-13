from pathlib import Path

import yaml

WORKFLOWS = (
    "phase-12-8a-license-graph-preflight.yml",
    "phase-12-8a-linux-x86-pilot.yml",
    "phase-13-readiness-gate.yml",
)


def test_phase128a_workflows_parse_and_avoid_runner_context_in_env(repository_root: Path) -> None:
    workflow_root = repository_root / ".github" / "workflows"
    for name in WORKFLOWS:
        path = workflow_root / name
        source = path.read_text(encoding="utf-8")
        assert yaml.safe_load(source) is not None
        assert "${{ runner.temp }}" not in source


def test_phase13_gate_accepts_v2_split_readiness(repository_root: Path) -> None:
    path = repository_root / ".github/workflows/phase-13-readiness-gate.yml"
    source = path.read_text(encoding="utf-8")
    assert "archguard.phase-13-readiness/v2" in source
    assert ".phase_12_complete == true" in source
    assert ".phase_13_scientifically_ready == true" in source
    assert ".phase_13_ready == .phase_13_operationally_ready" in source


def test_phase13_experiment_validates_evidence_without_git_history(
    repository_root: Path,
) -> None:
    path = repository_root / ".github/workflows/phase-13-experiment.yml"
    source = path.read_text(encoding="utf-8")
    assert yaml.safe_load(source) is not None
    assert "git merge-base" not in source
    assert "uv run archguard readiness gate" in source
    assert ".phase_12_complete == true" in source
    assert ".phase_13_operationally_ready == true" in source
    assert "421f3129ef6bee5883c41d05f087d6faff5b2a3de3b2ea543b4d27ade1488886" in source
    assert "93494690f402d17e511d9cad1fdc92907d408ae3a923139d30537894f9ab8ce7" in source
    assert "2ff4adc5be719608860845d68be15c07205bf563423099a30c617e3d29170d7d" in source


def test_external_workspace_is_initialized_at_runtime_before_use(repository_root: Path) -> None:
    path = repository_root / ".github" / "workflows" / WORKFLOWS[0]
    source = path.read_text(encoding="utf-8")
    initialization = source.index("- name: Initialize isolated paths")
    first_consumer = source.index("- name: Acquire immutable revisions and generate evidence twice")
    cleanup = source.index("- name: Cleanup Phase 12.8B temporary data")

    assert initialization < first_consumer < cleanup
    assert 'external_root="${RUNNER_TEMP}/archguard-phase-12-8b-external"' in source
    assert 'mkdir -p "${external_root}"' in source
    assert 'echo "EXTERNAL_ROOT=${external_root}" >> "${GITHUB_ENV}"' in source
    assert source.index('rm -rf -- "${EXTERNAL_ROOT') > initialization


def test_phase128b_executes_real_bounded_evidence_without_claiming_readiness(
    repository_root: Path,
) -> None:
    path = repository_root / ".github" / "workflows" / WORKFLOWS[0]
    source = path.read_text(encoding="utf-8")

    assert "250 MiB" in source
    assert "phase128b produce" in source
    assert source.count("generate evidence twice") >= 1
    assert "phase128b validate" in source
    assert "actions/upload-artifact@v7" in source
    assert "retention-days: 14" in source
    assert "GITHUB_STEP_SUMMARY" in source
    assert "Phase 13 readiness: `false`" in source
    assert "permissions:\n  contents: read" in source
