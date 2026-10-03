import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_imports_have_no_operational_side_effects(tmp_path: Path) -> None:
    script = """
import importlib
import logging
import pkgutil
import archguard
# Warm third-party imports: their package metadata reads are outside our contract.
import fastapi
import typer
import pydantic_settings
import yaml
from unittest.mock import patch
before = list(logging.getLogger().handlers)
with patch("pathlib.Path.read_text", side_effect=AssertionError("read on import")), \\
     patch("pathlib.Path.mkdir", side_effect=AssertionError("mkdir on import")), \\
     patch("logging.Logger.addHandler", side_effect=AssertionError("handler on import")), \\
     patch("subprocess.run", side_effect=AssertionError("execution on import")), \\
     patch("socket.socket.connect", side_effect=AssertionError("network on import")):
    for module in pkgutil.walk_packages(archguard.__path__, archguard.__name__ + "."):
        importlib.import_module(module.name)
assert logging.getLogger().handlers == before
"""
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=tmp_path, capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stderr
    assert not result.stdout
    assert not list(tmp_path.iterdir())


def test_module_entrypoint() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "archguard", "version"], capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "0.12.8"
