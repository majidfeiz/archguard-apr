import ast
import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.architecture


def violations(source: str, module: str) -> list[str]:
    """Allow only standard library and the core's explicitly permitted layers."""
    tree = ast.parse(source)
    package = module.rsplit(".", 1)[0]
    layer = module.split(".")[1]
    allowed = {"archguard.domain"}
    if layer == "application":
        allowed.add("archguard.application")
    errors: list[str] = []
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                base = importlib.util.resolve_name("." * node.level + base, package)
            names = [base] + [base + "." + alias.name for alias in node.names]
        elif isinstance(node, ast.Call):
            func = node.func
            if (isinstance(func, ast.Name) and func.id in {"__import__", "eval", "exec"}) or (
                isinstance(func, ast.Attribute) and func.attr == "import_module"
            ):
                errors.append("dynamic loading")
        for name in names:
            root = name.split(".")[0]
            if root in {"importlib", "runpy"}:
                errors.append(name)
            elif root not in sys.stdlib_module_names and not any(
                name == a or name.startswith(a + ".") for a in allowed
            ):
                errors.append(name)
    return errors


def test_repository_dependencies(repository_root: Path) -> None:
    source_root = repository_root / "src"
    for layer in ["domain", "application"]:
        for path in (source_root / "archguard" / layer).rglob("*.py"):
            module = ".".join(path.relative_to(source_root).with_suffix("").parts)
            assert not violations(path.read_text(), module), str(path)


@pytest.mark.parametrize(
    "source",
    [
        "import archguard.application",
        "from archguard import infrastructure",
        "from ..entrypoints import cli",
        "import fastapi",
        "import typer",
        "import openai",
        "from anthropic import Client",
        "import mcp",
        "import codex",
        "import claude",
        "import langgraph",
        "__import__('openai')",
        "import importlib as loader",
        "from .. import application",
    ],
)
def test_domain_rejects_forbidden(source: str) -> None:
    assert violations(source, "archguard.domain.models")


@pytest.mark.parametrize(
    "source",
    [
        "from archguard.infrastructure import config",
        "import archguard.entrypoints",
        "import openai",
        "import fastapi",
    ],
)
def test_application_rejects_forbidden(source: str) -> None:
    assert violations(source, "archguard.application.service")


def test_allowed_dependencies() -> None:
    assert not violations(
        "from .enums import Severity\nfrom dataclasses import dataclass", "archguard.domain.models"
    )
    assert not violations(
        "from archguard.domain.models import ExecutionResult",
        "archguard.application.ports.execution",
    )
