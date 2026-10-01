import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("fixture", ["synthetic", "bugsinpy-compatible", "swe-bench-compatible"])
def test_fixture_demo_is_deterministic(repository_root: Path, tmp_path: Path, fixture: str) -> None:
    outputs = [tmp_path / "one.json", tmp_path / "two.json"]
    for output in outputs:
        subprocess.run(
            [
                sys.executable,
                str(repository_root / "scripts/benchmark_fixture_demo.py"),
                "--fixture",
                fixture,
                "--output",
                str(output),
            ],
            check=True,
        )
    assert outputs[0].read_bytes() == outputs[1].read_bytes()
    value = json.loads(outputs[0].read_text())
    assert value["status"] == "fixture_verified"
    assert value["external_benchmark_verified"] is False
