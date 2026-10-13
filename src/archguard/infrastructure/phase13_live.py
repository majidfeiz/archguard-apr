"""Native-Linux live adapter for the frozen Phase 13 experiment.

Source-bearing data lives only under an owned temporary root and is never returned
from this adapter. Commands are fixed by reviewed evaluator metadata, never by the
provider response.
"""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, TypedDict, cast

from archguard.application.ports.phase13 import ProviderAttemptError, TreatmentRequest
from archguard.domain.phase13 import (
    MODEL,
    ExecutionResult,
    ProviderUsage,
    TerminalClassification,
    experiment_id,
)
from archguard.infrastructure.patch_inspector import UnifiedDiffInspector
from archguard.infrastructure.provider_preflight import load_phase13_provider_configuration

_REPOSITORIES = {
    "PySnooper": "https://github.com/cool-RR/PySnooper",
    "Black": "https://github.com/psf/black",
}
_REVISIONS = {
    "PySnooper-2": "e21a31162f4c54be693d8ca8260e42393b39abd3",
    "PySnooper-3": "6e3d797be3fa0a746fb5b1b7c7fea78eb926c208",
    "black-4": "65ea568e3301951f26e0e3b98f6d5dc80132e917",
}
_TASKS = {
    "PySnooper-2": (
        "Repair PySnooper custom_repr handling: a (list, callable) custom representation "
        "must format list values without raising TypeError."
    ),
    "PySnooper-3": "Repair the defect exercised by the frozen PySnooper file-output task.",
    "black-4": "Repair the defect exercised by the frozen Black beginning-backslash task.",
}
_RETRYABLE = frozenset({408, 429, 500, 502, 503, 504})


class Evaluation(TypedDict):
    architecture_status: str
    architecture_violations: tuple[tuple[str, int], ...]
    evaluator_executed: bool
    buggy_failure_reproduced: bool
    candidate_test_outcome: str
    tests_fixed: int
    regressions: int
    repair_success: bool
    classification: TerminalClassification


class Phase13LiveExecutor:
    def __init__(
        self, repository_root: Path, provider_config: Path, protocol_fingerprint: str
    ) -> None:
        if os.uname().sysname != "Linux" or os.uname().machine != "x86_64":
            raise ValueError("native Linux x86_64 required")
        self.repository_root = repository_root.resolve()
        self.configuration = load_phase13_provider_configuration(provider_config)
        self.protocol_fingerprint = protocol_fingerprint
        self.root = Path(tempfile.mkdtemp(prefix="archguard-phase13-"))
        self._owned: list[Path] = []

    def execute(self, request: TreatmentRequest, *, retry: bool = False) -> ExecutionResult:
        started = time.monotonic()
        workspace = self.root / f"run-{request.identity.ordinal}"
        source = workspace / "source"
        workspace.mkdir(mode=0o700)
        self._checkout(request, source)
        context, context_fingerprint = self._context(request, source)
        if context_fingerprint != request.context_manifest_fingerprint:
            # The request fingerprint represents policy; bind the actual selection separately.
            context_fingerprint = hashlib.sha256(context.encode()).hexdigest()
        patch, response_fingerprint, usage = self._invoke(request, context)
        patch_bytes = patch.encode("utf-8")
        patch_fingerprint = hashlib.sha256(patch_bytes).hexdigest()
        parsed = UnifiedDiffInspector().inspect(patch_bytes)
        applied = False
        buggy = workspace / "buggy"
        rejection = None if parsed.acceptable else "patch_policy_rejection"
        evaluation: Evaluation = {
            "architecture_status": "skipped",
            "architecture_violations": (),
            "evaluator_executed": False,
            "buggy_failure_reproduced": False,
            "candidate_test_outcome": "not_run",
            "tests_fixed": 0,
            "regressions": 0,
            "repair_success": False,
            "classification": TerminalClassification.INVALID_PATCH,
        }
        try:
            if parsed.acceptable:
                try:
                    subprocess.run(
                        [
                            "git",
                            "-c",
                            "core.hooksPath=/dev/null",
                            "worktree",
                            "add",
                            "--detach",
                            str(buggy),
                            _REVISIONS[request.identity.task_id],
                        ],
                        cwd=source,
                        check=True,
                        capture_output=True,
                        timeout=120,
                    )
                    self._git_apply(source, patch_bytes)
                    applied = True
                    evaluation = cast(Evaluation, self._evaluate(request, buggy, source))
                except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
                    rejection = "patch_application_failure" if not applied else None
                    evaluation["classification"] = (
                        TerminalClassification.INVALID_PATCH
                        if not applied
                        else TerminalClassification.EVALUATOR_FAILURE
                    )
        finally:
            shutil.rmtree(workspace, ignore_errors=True)
        added = sum(
            line.startswith("+") and not line.startswith("+++") for line in patch.splitlines()
        )
        deleted = sum(
            line.startswith("-") and not line.startswith("---") for line in patch.splitlines()
        )
        observed = self._cost(usage)
        return ExecutionResult(
            experiment_id(self.protocol_fingerprint),
            request.identity,
            _REVISIONS[request.identity.task_id],
            self.protocol_fingerprint,
            request.request_fingerprint,
            context_fingerprint,
            response_fingerprint,
            patch_fingerprint,
            parsed.acceptable,
            applied,
            len(parsed.changed_paths),
            added,
            deleted,
            rejection,
            str(evaluation["architecture_status"]),
            tuple(evaluation["architecture_violations"]),
            bool(evaluation["evaluator_executed"]),
            bool(evaluation["buggy_failure_reproduced"]),
            str(evaluation["candidate_test_outcome"]),
            int(evaluation["tests_fixed"]),
            int(evaluation["regressions"]),
            bool(evaluation["repair_success"]),
            evaluation["classification"],
            usage,
            observed,
            2 if retry else 1,
            _duration_bucket(time.monotonic() - started),
            "complete",
            request.provider_call_id,
        )

    def cleanup(self) -> bool:
        for label in ("org.archguard.phase=13", "archguard.phase=12.8f"):
            containers = subprocess.run(
                ["docker", "ps", "-aq", "--filter", f"label={label}"],
                capture_output=True,
                check=False,
                text=True,
            ).stdout.split()
            if containers:
                subprocess.run(
                    ["docker", "rm", "-f", *containers], capture_output=True, check=False
                )
            images = subprocess.run(
                ["docker", "images", "-q", "--filter", f"label={label}"],
                capture_output=True,
                check=False,
                text=True,
            ).stdout.split()
            if images:
                subprocess.run(
                    ["docker", "image", "rm", "-f", *images],
                    capture_output=True,
                    check=False,
                )
        shutil.rmtree(self.root, ignore_errors=True)
        return not self.root.exists()

    def _checkout(self, request: TreatmentRequest, destination: Path) -> None:
        repository = _REPOSITORIES[request.identity.project]
        revision = _REVISIONS[request.identity.task_id]
        environment = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_LFS_SKIP_SMUDGE": "1"}
        subprocess.run(
            [
                "git",
                "-c",
                "core.hooksPath=/dev/null",
                "clone",
                "--no-checkout",
                "--no-recurse-submodules",
                "--filter=blob:none",
                repository,
                str(destination),
            ],
            check=True,
            capture_output=True,
            env=environment,
            timeout=300,
        )
        subprocess.run(
            ["git", "-c", "core.hooksPath=/dev/null", "checkout", "--detach", revision],
            cwd=destination,
            check=True,
            capture_output=True,
            env=environment,
            timeout=120,
        )
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=destination,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if head != revision:
            raise ValueError("immutable revision mismatch")
        modes = subprocess.run(
            ["git", "ls-tree", "-r", "HEAD"],
            cwd=destination,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        if any(line.startswith(("120000 ", "160000 ")) for line in modes.splitlines()):
            raise ValueError("symlink or gitlink rejected")

    def _context(self, request: TreatmentRequest, source: Path) -> tuple[str, str]:
        selected: list[str] = []
        total = 0
        for path in sorted(
            source.rglob("*.py"), key=lambda item: item.relative_to(source).as_posix()
        ):
            relative = path.relative_to(source).as_posix()
            if "/tests/" in f"/{relative}" or relative.startswith("tests/") or path.is_symlink():
                continue
            raw = path.read_bytes()
            if total + len(raw) > 120_000:
                continue
            text = raw.decode("utf-8", "replace")
            selected.append(f"FILE {relative}\n{text}")
            total += len(raw)
        treatment = ""
        if request.architecture_treatment:
            architecture = self._architecture_context(request, source)
            treatment = (
                "\nARCHITECTURE TREATMENT: preserve existing package boundaries, dependency "
                "direction, public APIs, and source-free graph relationships. Architecture "
                "conformance is mandatory.\n" + architecture
            )
        body = (
            _TASKS[request.identity.task_id]
            + "\nReturn exactly one Git unified diff. Do not return commands or prose."
            + treatment
            + "\n\n"
            + "\n\n".join(selected)
        )
        return body, hashlib.sha256(
            json.dumps([item.split("\n", 1)[0] for item in selected], sort_keys=True).encode()
        ).hexdigest()

    def _architecture_context(self, request: TreatmentRequest, source: Path) -> str:
        root = source.parent / "architecture-context"
        root.mkdir()
        snapshot = root / "snapshot.json"
        graph = root / "graph.json"
        commands = (
            [
                "uv",
                "run",
                "archguard",
                "repository",
                "analyze",
                str(source),
                "--output",
                str(snapshot),
            ],
            [
                "uv",
                "run",
                "archguard",
                "graph",
                "build",
                "--snapshot",
                str(snapshot),
                "--output",
                str(graph),
            ],
        )
        for command in commands:
            subprocess.run(command, check=True, capture_output=True, timeout=300)
        graph_value = json.loads(graph.read_text(encoding="utf-8"))
        treatment: dict[str, Any] = {
            "graph_fingerprint": graph_value.get("graph_fingerprint"),
            "nodes": graph_value.get("nodes", ()),
            "edges": graph_value.get("edges", ()),
        }
        if request.identity.project == "PySnooper":
            profile = root / "profile.json"
            subprocess.run(
                [
                    "uv",
                    "run",
                    "archguard",
                    "architecture",
                    "profile",
                    "compile",
                    str(
                        self.repository_root
                        / "configs/external-profiles/pysnooper-micro-pilot-amended-v2.yaml"
                    ),
                    "--output",
                    str(profile),
                ],
                check=True,
                capture_output=True,
                timeout=300,
            )
            treatment["profile"] = json.loads(profile.read_text(encoding="utf-8"))
        else:
            treatment["profile"] = {"applicability": "no_frozen_project_profile"}
        return json.dumps(treatment, sort_keys=True, separators=(",", ":"))[:30_000]

    def _invoke(self, request: TreatmentRequest, context: str) -> tuple[str, str, ProviderUsage]:
        from openai import OpenAI

        client = OpenAI(
            api_key=os.environ["OPENAI_API_KEY"],
            max_retries=0,
            timeout=self.configuration.timeout_seconds,
        )
        try:
            response = client.responses.create(
                model=MODEL,
                input=[{"role": "developer", "content": context}],
                max_output_tokens=self.configuration.maximum_output_tokens,
                store=False,
                tools=[],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "candidate_patch",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {"patch": {"type": "string"}},
                            "required": ["patch"],
                            "additionalProperties": False,
                        },
                    }
                },
            )
        except Exception as error:
            status = getattr(error, "status_code", None)
            provider_code = str(getattr(error, "code", "") or "").lower()
            category = (
                "timeout"
                if status == 408 or isinstance(error, TimeoutError)
                else "quota_failure"
                if status == 429
                and provider_code
                in {"billing_hard_limit_reached", "insufficient_quota", "quota_exceeded"}
                else "rate_limit"
                if status == 429
                else "provider_5xx"
                if status in {500, 502, 503, 504}
                else "connection_failure"
                if isinstance(error, ConnectionError)
                else "authentication_failure"
                if status in {401, 403}
                else "quota_failure"
                if status == 402
                else "provider_failure"
            )
            raise ProviderAttemptError(category) from error
        if str(getattr(response, "model", "")) != MODEL:
            raise ProviderAttemptError("model_identity_failure")
        if getattr(response, "usage", None) is None:
            raise ProviderAttemptError("usage_schema_failure")
        raw = response.output_text
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            raise ProviderAttemptError("invalid_patch_response") from None
        if (
            not isinstance(payload, dict)
            or set(payload) != {"patch"}
            or not isinstance(payload["patch"], str)
        ):
            raise ProviderAttemptError("invalid_patch_response")
        response_usage = response.usage
        if response_usage is None:
            raise ProviderAttemptError("usage_schema_failure")
        detail_in = getattr(response_usage, "input_tokens_details", None)
        detail_out = getattr(response_usage, "output_tokens_details", None)
        try:
            usage = ProviderUsage(
                int(response_usage.input_tokens),
                int(getattr(detail_in, "cached_tokens", 0) or 0),
                int(response_usage.output_tokens),
                int(getattr(detail_out, "reasoning_tokens", 0) or 0),
            )
        except (TypeError, ValueError):
            raise ProviderAttemptError("usage_schema_failure") from None
        if (
            usage.input_tokens > self.configuration.maximum_input_tokens
            or usage.output_tokens > self.configuration.maximum_output_tokens
        ):
            raise ProviderAttemptError("usage_schema_failure")
        return payload["patch"], hashlib.sha256(raw.encode()).hexdigest(), usage

    @staticmethod
    def _git_apply(source: Path, patch: bytes) -> None:
        process = subprocess.run(
            ["git", "apply", "--check", "--whitespace=error-all", "-"],
            cwd=source,
            input=patch,
            capture_output=True,
        )
        if process.returncode != 0:
            raise ValueError("patch application rejected")
        subprocess.run(
            ["git", "apply", "--whitespace=error-all", "-"],
            cwd=source,
            input=patch,
            check=True,
            capture_output=True,
        )

    def _evaluate(self, request: TreatmentRequest, buggy: Path, candidate: Path) -> dict[str, Any]:
        # Keep the reviewed tooling behind an explicit process boundary: infrastructure
        # must not depend on the repository's scripts/test component.
        command = [
            "uv",
            "run",
            "python",
            str(self.repository_root / "scripts/phase13_candidate_evaluator.py"),
            "--task-id",
            request.identity.task_id,
            "--buggy",
            str(buggy),
            "--candidate",
            str(candidate),
            "--root",
            str(self.root / f"evaluator-{request.identity.ordinal}"),
            "--repository-root",
            str(self.repository_root),
        ]
        if request.architecture_treatment:
            command.append("--architecture-treatment")
        process = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=3600,
        )
        value = json.loads(process.stdout)
        if not isinstance(value, dict):
            raise ValueError("invalid evaluator result")
        value["architecture_violations"] = tuple(
            (str(severity), int(count)) for severity, count in value["architecture_violations"]
        )
        value["classification"] = TerminalClassification(value["classification"])
        return value

    def _cost(self, usage: ProviderUsage) -> Decimal:
        prices = self.configuration.prices
        uncached = usage.input_tokens - usage.cached_input_tokens
        return (
            Decimal(uncached) * prices.input
            + Decimal(usage.cached_input_tokens) * prices.cached_input
            + Decimal(usage.output_tokens) * prices.output
        ) / Decimal(prices.unit_tokens)


def _duration_bucket(seconds: float) -> str:
    if seconds < 60:
        return "under_1_minute"
    if seconds < 300:
        return "1_to_5_minutes"
    if seconds < 1200:
        return "5_to_20_minutes"
    return "20_minutes_or_more"
