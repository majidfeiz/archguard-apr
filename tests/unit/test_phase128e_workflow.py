from pathlib import Path

import yaml


def test_phase128e_workflow_contract(repository_root: Path) -> None:
    path = repository_root / ".github/workflows/phase-12-8e-license-candidate-preflight.yml"
    raw = path.read_text()
    workflow = yaml.safe_load(raw)
    assert "workflow_dispatch" in workflow[True]
    assert workflow["permissions"] == {"contents": "read"}
    assert "${{ runner.temp }}" not in raw
    assert "${RUNNER_TEMP}" in raw
    assert "timeout-minutes: 20" in raw
    assert "max-parallel: 1" in raw
    assert "536870912" in raw and "2147483648" in raw
    assert "archguard-phase-12-8e-license-candidate-${{ github.run_id }}" in raw
    assert "retention-days: 14" in raw
    assert "phase128e_preflight.py" in raw
    assert "cmp --silent" in raw
    assert "if: always()" in raw
    assert "docker ps" in raw and "docker volume ls" in raw and "docker buildx ls" in raw


def test_exact_flat_artifact_allowlist(repository_root: Path) -> None:
    raw = (
        repository_root / ".github/workflows/phase-12-8e-license-candidate-preflight.yml"
    ).read_text()
    expected = {
        "manifest.json",
        "license-summary.json",
        "candidate-pool-summary.json",
        "selection-determinism.json",
        "security-scan-summary.json",
        "cleanup-summary.json",
        "readiness-summary.json",
        "SHA256SUMS",
    }
    block = raw.split("expected=(", 1)[1].split(")", 1)[0]
    assert set(block.replace('"', "").split()) == expected
    assert "uses: actions/upload-artifact@v7" in raw
