import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from archguard.entrypoints.cli.app import app

runner = CliRunner()


def git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def fixture(tmp_path: Path) -> tuple[Path, Path, Path, str]:
    repository = tmp_path / "repo"
    source = repository / "src/demo"
    source.mkdir(parents=True)
    git(repository, "init", "-b", "main")
    git(repository, "config", "user.email", "test@example.invalid")
    git(repository, "config", "user.name", "ArchGuard Test")
    (source / "__init__.py").write_text("")
    (source / "model.py").write_text("VALUE = 1\n")
    (source / "service.py").write_text("from . import model\n")
    git(repository, "add", ".")
    git(repository, "commit", "-m", "baseline")
    baseline = git(repository, "rev-parse", "HEAD")
    (source / "service.py").write_text("from . import model\nVALUE = 2\n")
    patch = tmp_path / "candidate.diff"
    patch.write_text(git(repository, "diff") + "\n")
    git(repository, "checkout", "--", "src/demo/service.py")
    profile = tmp_path / "profile.yaml"
    profile.write_text(
        """architecture_profile_schema_version: "1"
id: smoke
name: Smoke profile
assignment: {unassigned: warn, ambiguous: error}
components:
  - id: application
    selectors: [{type: module_prefix, value: demo}]
rules:
  - id: no-cycle
    type: forbid_cycles
    components: [application]
"""
    )
    return repository, patch, profile, baseline


def test_complete_cli_is_deterministic_and_inspectable(tmp_path: Path) -> None:
    repository, patch, profile, baseline = fixture(tmp_path)
    inspect = runner.invoke(app, ["patch", "inspect", str(patch)])
    assert inspect.exit_code == 0
    assert json.loads(inspect.stdout)["acceptable"] is True
    outputs = [tmp_path / "one.json", tmp_path / "two.json"]
    for output in outputs:
        result = runner.invoke(
            app,
            [
                "patch",
                "validate",
                str(repository),
                "--patch",
                str(patch),
                "--profile",
                str(profile),
                "--baseline",
                baseline,
                "--source-root",
                "src",
                "--output",
                str(output),
            ],
        )
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["architecture_passed"] is True
    assert outputs[0].read_bytes() == outputs[1].read_bytes()
    for command in (
        ["result", "inspect"],
        ["result", "delta"],
        ["result", "violations", "--state", "all"],
    ):
        result = runner.invoke(app, ["patch", *command, str(outputs[0])])
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout) is not None
    assert git(repository, "status", "--porcelain") == ""
    assert "archguard-candidate-" not in git(repository, "worktree", "list", "--porcelain")


def test_rejected_patch_has_stable_code_and_no_content_leak(tmp_path: Path) -> None:
    patch = tmp_path / "unsafe.diff"
    secret = "DO_NOT_PRINT_THIS_HUNK"
    patch.write_text(
        "diff --git a/../x b/../x\n--- a/../x\n+++ b/../x\n@@ -1 +1 @@\n-old\n+" + secret + "\n"
    )
    result = runner.invoke(app, ["patch", "inspect", str(patch)])
    assert result.exit_code == 3
    assert "unsafe_path" in result.stdout
    assert secret not in result.stdout
