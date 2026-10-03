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


def test_external_workspace_is_initialized_at_runtime_before_use(repository_root: Path) -> None:
    path = repository_root / ".github" / "workflows" / WORKFLOWS[0]
    source = path.read_text(encoding="utf-8")
    initialization = source.index("- name: Initialize external workspace")
    first_consumer = source.index("- name: Fail closed pending explicit acquisition adapter")
    cleanup = source.index("- name: Cleanup only Phase 12.8A external data")

    assert initialization < first_consumer < cleanup
    assert 'external_root="${RUNNER_TEMP}/archguard-phase-12-8a-external"' in source
    assert 'mkdir -p "${external_root}"' in source
    assert 'echo "EXTERNAL_ROOT=${external_root}" >> "${GITHUB_ENV}"' in source
    assert source.index('if [ -d "$EXTERNAL_ROOT" ]') > initialization
