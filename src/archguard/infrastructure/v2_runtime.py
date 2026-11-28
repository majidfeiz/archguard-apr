"""Owned workspaces, fake/real providers and controlled V2.2 candidate processing."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any

from archguard.application.ports.v2_execution import (
    CandidateAssessment,
    PreparedRequest,
    ProviderAdmissionFailure,
    ProviderChargedFailure,
    ProviderOutcome,
)
from archguard.domain.canonical import canonical_json
from archguard.domain.providers import ProviderErrorCategory, ProviderFailure
from archguard.domain.v2_execution import (
    ExecutionIdentity,
    ProviderFailureDiagnostic,
    ProviderFailureKind,
    StageStatus,
    TerminalClassification,
)
from archguard.domain.v2_micro_pilot import (
    INPUT_PER_MILLION,
    MAX_INPUT_TOKENS,
    MAX_OUTPUT_TOKENS,
    MODEL_SNAPSHOT,
    OUTPUT_PER_MILLION,
    SyntheticUsage,
)
from archguard.infrastructure.json_codec import unique_object
from archguard.infrastructure.providers.configuration import ProviderSettings, RetryPolicy
from archguard.infrastructure.providers.credentials import credential_for
from archguard.infrastructure.providers.openai_responses import OpenAIResponsesAdapter
from archguard.infrastructure.providers.redaction import request_id_hash
from archguard.infrastructure.providers.retry import ProviderInvocationError
from archguard.infrastructure.v2_patch_response import StrictRepairResponseExtractor
from archguard.infrastructure.v2_protocol import FrozenProtocol

TASK_TEXT = {
    "PySnooper-2": (
        "Repair PySnooper custom_repr handling: a (list, callable) custom representation "
        "must format list values without raising TypeError."
    ),
    "PySnooper-3": "Repair the defect exercised by the frozen PySnooper file-output task.",
}
CAPABILITY_PROBE_MAX_INPUT_TOKENS = 1_000
CAPABILITY_PROBE_MAX_OUTPUT_TOKENS = 128
CAPABILITY_PROBE_MAX_COST_USD = Decimal("0.0050")


@dataclass(frozen=True)
class CapabilityProbeResult:
    schema: str
    status: str
    model: str
    api: str
    stage: str
    strict_schema_accepted: bool
    response_structure_valid: bool
    patch_semantics_valid: bool
    tools_disabled: bool
    provider_request_attempts: int
    accepted_provider_calls: int
    scientific_executions: int
    usage_returned: bool
    input_tokens: int
    output_tokens: int
    observed_cost_usd: str
    diagnostic_fingerprint: str

    def as_source_free_dict(self) -> dict[str, object]:
        return asdict(self)


class CapabilityProbeStage(StrEnum):
    LOCAL_ADMISSION = "LOCAL_ADMISSION"
    PROVIDER_REQUEST = "PROVIDER_REQUEST"
    PROVIDER_RESPONSE = "PROVIDER_RESPONSE"
    USAGE_RECONCILIATION = "USAGE_RECONCILIATION"
    STRUCTURED_RESPONSE_VALIDATION = "STRUCTURED_RESPONSE_VALIDATION"
    PATCH_SEMANTIC_VALIDATION = "PATCH_SEMANTIC_VALIDATION"


class CapabilityProbeStatus(StrEnum):
    PRE_PROVIDER_BLOCKED = "PRE_PROVIDER_BLOCKED"
    PROVIDER_REJECTED = "PROVIDER_REJECTED"
    PROVIDER_ACCEPTED_RESPONSE_INVALID = "PROVIDER_ACCEPTED_RESPONSE_INVALID"
    PROVIDER_ACCEPTED_USAGE_INVALID = "PROVIDER_ACCEPTED_USAGE_INVALID"
    SUPPORTED = "SUPPORTED"


class CapabilityProbeFailure(RuntimeError):
    def __init__(self, result: CapabilityProbeResult) -> None:
        super().__init__("source-free capability probe failure")
        self.result = result


def diagnostic(label: str) -> str:
    return hashlib.sha256(
        canonical_json({"schema": "archguard.v2-diagnostic/v1", "code": label})
    ).hexdigest()


FAILURE_TAXONOMY = {
    ProviderErrorCategory.AUTHENTICATION: ProviderFailureKind.AUTHENTICATION,
    ProviderErrorCategory.PERMISSION: ProviderFailureKind.PERMISSION_MODEL_ACCESS,
    ProviderErrorCategory.UNSUPPORTED_MODEL: ProviderFailureKind.PERMISSION_MODEL_ACCESS,
    ProviderErrorCategory.INVALID_REQUEST: ProviderFailureKind.INVALID_REQUEST,
    ProviderErrorCategory.MALFORMED_OUTPUT: ProviderFailureKind.SCHEMA_REJECTION,
    ProviderErrorCategory.INCOMPLETE: ProviderFailureKind.SCHEMA_REJECTION,
    ProviderErrorCategory.OUTPUT_LIMIT: ProviderFailureKind.SCHEMA_REJECTION,
    ProviderErrorCategory.UNSUPPORTED_CAPABILITY: ProviderFailureKind.SCHEMA_REJECTION,
    ProviderErrorCategory.RATE_LIMITED: ProviderFailureKind.RATE_LIMIT,
    ProviderErrorCategory.NETWORK: ProviderFailureKind.NETWORK_TRANSPORT,
    ProviderErrorCategory.TIMEOUT: ProviderFailureKind.NETWORK_TRANSPORT,
    ProviderErrorCategory.CANCELLED: ProviderFailureKind.NETWORK_TRANSPORT,
    ProviderErrorCategory.OVERLOADED: ProviderFailureKind.SERVER_ERROR,
    ProviderErrorCategory.UNAVAILABLE: ProviderFailureKind.SERVER_ERROR,
}


def safe_provider_diagnostic(failure: ProviderFailure) -> ProviderFailureDiagnostic:
    return ProviderFailureDiagnostic(
        FAILURE_TAXONOMY.get(failure.category, ProviderFailureKind.UNKNOWN_PROVIDER_FAILURE),
        failure.stage,
        failure.retryable,
        failure.http_status,
        failure.provider_code,
        failure.usage_returned,
        request_id_hash(failure.request_id),
    )


class DeterministicFakeProvider:
    def __init__(self) -> None:
        self.calls: list[ExecutionIdentity] = []

    def invoke(self, request: PreparedRequest) -> ProviderOutcome:
        self.calls.append(request.identity)
        body = {
            "schema_version": "archguard.repair-response/v2.1",
            "task_id": request.identity.task_id,
            "candidate_id": f"fake-{request.identity.ordinal}",
            "unified_diff": (
                "diff --git a/pysnooper/tracer.py b/pysnooper/tracer.py\n"
                "--- a/pysnooper/tracer.py\n+++ b/pysnooper/tracer.py\n"
                "@@ -1 +1 @@\n-old\n+new\n"
            ),
            "declared_changed_paths": ["pysnooper/tracer.py"],
        }
        return ProviderOutcome(canonical_json(body), SyntheticUsage(1000, 100))


class FakeProcessor:
    def process(self, request: PreparedRequest, response: bytes) -> CandidateAssessment:
        extracted = StrictRepairResponseExtractor().extract(response)
        if extracted.normalized_patch is None:
            return CandidateAssessment(
                StageStatus.FAILED,
                StageStatus.NOT_RUN,
                StageStatus.NOT_RUN,
                StageStatus.NOT_RUN,
                TerminalClassification.EXTRACTION_FAILURE,
                tuple(item.fingerprint for item in extracted.diagnostics),
            )
        architecture = (
            StageStatus.PASSED
            if request.identity.condition in {"GRAPH_CONSTRAINTS", "FULL_ARCHGUARD"}
            else StageStatus.NOT_REQUIRED
        )
        return CandidateAssessment(
            StageStatus.PASSED,
            StageStatus.PASSED,
            StageStatus.PASSED,
            architecture,
            TerminalClassification.SUCCESSFUL_REPAIR,
        )


class NoopCleanup:
    def cleanup(self) -> bool:
        return True


class FakePreparer:
    def __init__(self, fairness_fingerprint: str) -> None:
        self.fairness_fingerprint = fairness_fingerprint

    def prepare(self, identity: ExecutionIdentity) -> PreparedRequest:
        return PreparedRequest(
            identity, f"deterministic fake request {identity.ordinal}", self.fairness_fingerprint
        )


class V2OpenAIProvider:
    """One Responses API request per invocation; retries and provider tools are disabled."""

    def invoke(self, request: PreparedRequest) -> ProviderOutcome:
        credential = credential_for("openai")
        if not credential.configured:
            raise ValueError("OPENAI_API_KEY is not configured")
        settings = ProviderSettings(
            provider="openai",
            model=MODEL_SNAPSHOT,
            request_timeout_seconds=600,
            maximum_output_units=MAX_OUTPUT_TOKENS,
            retry=RetryPolicy(maximum_attempts=1),
            structured_output_mode="strict_json_schema",
            reasoning_effort="medium",
            stateless=True,
            model_allowlist=(MODEL_SNAPSHOT,),
            maximum_invocation_cost="0.1175",
        )
        try:
            raw, usage = OpenAIResponsesAdapter(settings, credential).invoke_v2_repair(
                request.prompt
            )
        except ProviderInvocationError as error:
            if error.usage is None:
                raise ProviderAdmissionFailure(safe_provider_diagnostic(error.failure)) from None
            try:
                measured = SyntheticUsage(error.usage.input_units, error.usage.output_units)
            except (TypeError, ValueError):
                raise ProviderAdmissionFailure(
                    ProviderFailureDiagnostic(
                        ProviderFailureKind.UNKNOWN_PROVIDER_FAILURE,
                        "usage_validation",
                        False,
                        None,
                        "invalid_usage",
                        True,
                        None,
                    )
                ) from None
            raise ProviderChargedFailure(
                measured,
                safe_provider_diagnostic(error.failure),
                error.response_state,
            ) from None
        try:
            measured = SyntheticUsage(usage.input_units, usage.output_units)
        except (TypeError, ValueError):
            raise ProviderAdmissionFailure(
                ProviderFailureDiagnostic(
                    ProviderFailureKind.UNKNOWN_PROVIDER_FAILURE,
                    "usage_validation",
                    False,
                    None,
                    "invalid_usage",
                    True,
                    None,
                )
            ) from None
        return ProviderOutcome(raw, measured)


class V2CapabilityProbe:
    """One operational request; never part of the eight scientific executions."""

    def run(self) -> CapabilityProbeResult:
        try:
            self._admit()
            settings = ProviderSettings(
                provider="openai",
                model=MODEL_SNAPSHOT,
                request_timeout_seconds=120,
                maximum_output_units=CAPABILITY_PROBE_MAX_OUTPUT_TOKENS,
                retry=RetryPolicy(maximum_attempts=1),
                structured_output_mode="strict_json_schema",
                reasoning_effort="none",
                stateless=True,
                model_allowlist=(MODEL_SNAPSHOT,),
                maximum_invocation_cost=str(CAPABILITY_PROBE_MAX_COST_USD),
            )
            credential = credential_for("openai")
            if not credential.configured:
                raise ValueError("provider credential is not configured")
        except (TypeError, ValueError):
            raise CapabilityProbeFailure(
                self._result(
                    CapabilityProbeStatus.PRE_PROVIDER_BLOCKED,
                    CapabilityProbeStage.LOCAL_ADMISSION,
                    diagnostic_fingerprint=diagnostic("probe_local_admission"),
                )
            ) from None
        prompt = (
            "Operational capability probe only. Return the smallest valid "
            "archguard.repair-response/v2.1 JSON object with a minimal syntactically valid "
            "unified diff. No repository source is supplied."
        )
        try:
            raw, usage = OpenAIResponsesAdapter(settings, credential).invoke_v2_repair(prompt)
        except ProviderInvocationError as error:
            provider_diagnostic = safe_provider_diagnostic(error.failure)
            raise CapabilityProbeFailure(
                self._result(
                    CapabilityProbeStatus.PROVIDER_REJECTED,
                    CapabilityProbeStage.PROVIDER_REQUEST,
                    attempts=1,
                    usage_returned=provider_diagnostic.usage_returned,
                    diagnostic_fingerprint=provider_diagnostic.fingerprint,
                )
            ) from None
        except Exception:
            raise CapabilityProbeFailure(
                self._result(
                    CapabilityProbeStatus.PROVIDER_ACCEPTED_RESPONSE_INVALID,
                    CapabilityProbeStage.PROVIDER_RESPONSE,
                    attempts=1,
                    diagnostic_fingerprint=diagnostic("probe_provider_response"),
                )
            ) from None
        try:
            input_tokens = self._usage_integer(usage.input_units)
            output_tokens = self._usage_integer(usage.output_units)
            observed = self._cost(input_tokens, output_tokens)
            if (
                input_tokens > CAPABILITY_PROBE_MAX_INPUT_TOKENS
                or output_tokens > CAPABILITY_PROBE_MAX_OUTPUT_TOKENS
                or observed > CAPABILITY_PROBE_MAX_COST_USD
            ):
                raise ValueError("probe usage contradicts reservation")
        except (TypeError, ValueError):
            safe_input = usage.input_units if type(usage.input_units) is int else 0
            safe_output = usage.output_units if type(usage.output_units) is int else 0
            safe_cost = self._cost(max(safe_input, 0), max(safe_output, 0))
            raise CapabilityProbeFailure(
                self._result(
                    CapabilityProbeStatus.PROVIDER_ACCEPTED_USAGE_INVALID,
                    CapabilityProbeStage.USAGE_RECONCILIATION,
                    attempts=1,
                    accepted=1,
                    usage_returned=True,
                    input_tokens=safe_input,
                    output_tokens=safe_output,
                    observed_cost=safe_cost,
                    strict_schema_accepted=True,
                    diagnostic_fingerprint=diagnostic("probe_usage_reconciliation"),
                )
            ) from None
        structure_valid = self._structure_valid(raw)
        if not structure_valid:
            raise CapabilityProbeFailure(
                self._result(
                    CapabilityProbeStatus.PROVIDER_ACCEPTED_RESPONSE_INVALID,
                    CapabilityProbeStage.STRUCTURED_RESPONSE_VALIDATION,
                    attempts=1,
                    accepted=1,
                    usage_returned=True,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    observed_cost=observed,
                    strict_schema_accepted=True,
                    diagnostic_fingerprint=diagnostic("probe_structured_response"),
                )
            ) from None
        extracted = StrictRepairResponseExtractor().extract(raw)
        return self._result(
            CapabilityProbeStatus.SUPPORTED,
            CapabilityProbeStage.PATCH_SEMANTIC_VALIDATION,
            attempts=1,
            accepted=1,
            usage_returned=True,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            observed_cost=observed,
            strict_schema_accepted=True,
            response_structure_valid=True,
            patch_semantics_valid=extracted.normalized_patch is not None,
            diagnostic_fingerprint=diagnostic("probe_supported"),
        )

    @staticmethod
    def _admit() -> None:
        maximum = V2CapabilityProbe._cost(
            CAPABILITY_PROBE_MAX_INPUT_TOKENS, CAPABILITY_PROBE_MAX_OUTPUT_TOKENS
        )
        if maximum > CAPABILITY_PROBE_MAX_COST_USD:
            raise ValueError("probe reservation exceeds hard ceiling")

    @staticmethod
    def _usage_integer(value: object) -> int:
        if type(value) is not int or value < 0:
            raise ValueError("invalid provider usage")
        return value

    @staticmethod
    def _cost(input_tokens: int, output_tokens: int) -> Decimal:
        return (
            Decimal(input_tokens) * INPUT_PER_MILLION + Decimal(output_tokens) * OUTPUT_PER_MILLION
        ) / Decimal(1_000_000)

    @staticmethod
    def _structure_valid(raw: bytes) -> bool:
        try:
            value = json.loads(raw, object_pairs_hook=unique_object)
        except (TypeError, ValueError, UnicodeDecodeError):
            return False
        if not isinstance(value, dict) or set(value) != {
            "schema_version",
            "task_id",
            "candidate_id",
            "unified_diff",
            "declared_changed_paths",
            "rationale_summary",
        }:
            return False
        return (
            value.get("schema_version") == "archguard.repair-response/v2.1"
            and all(
                isinstance(value.get(key), str)
                for key in ("task_id", "candidate_id", "unified_diff")
            )
            and isinstance(value.get("declared_changed_paths"), list)
            and all(isinstance(item, str) for item in value["declared_changed_paths"])
            and (
                value.get("rationale_summary") is None
                or isinstance(value["rationale_summary"], str)
            )
        )

    @staticmethod
    def _result(
        status: CapabilityProbeStatus,
        stage: CapabilityProbeStage,
        *,
        attempts: int = 0,
        accepted: int = 0,
        usage_returned: bool = False,
        input_tokens: int = 0,
        output_tokens: int = 0,
        observed_cost: Decimal = Decimal("0"),
        strict_schema_accepted: bool = False,
        response_structure_valid: bool = False,
        patch_semantics_valid: bool = False,
        diagnostic_fingerprint: str,
    ) -> CapabilityProbeResult:
        return CapabilityProbeResult(
            "archguard.v2-provider-capability-probe/v2",
            status.value,
            MODEL_SNAPSHOT,
            "responses",
            stage.value,
            strict_schema_accepted,
            response_structure_valid,
            patch_semantics_valid,
            True,
            attempts,
            accepted,
            0,
            usage_returned,
            input_tokens,
            output_tokens,
            format(observed_cost, "f"),
            diagnostic_fingerprint,
        )


class V2Workspace:
    """Owns source-bearing state; only source-free assessments leave this adapter."""

    def __init__(self, protocol: FrozenProtocol) -> None:
        if os.uname().sysname != "Linux" or os.uname().machine != "x86_64":
            raise ValueError("real execution requires Linux x86_64")
        self.protocol = protocol
        self.root = Path(tempfile.mkdtemp(prefix="archguard-v2-"))
        self.sources: dict[int, Path] = {}

    def prepare(self, identity: ExecutionIdentity) -> PreparedRequest:
        manifest = json.loads(
            (
                self.protocol.root / f"research/v2/manifests/{identity.task_id.lower()}.json"
            ).read_bytes()
        )
        source = self.root / f"run-{identity.ordinal}" / "candidate"
        source.parent.mkdir(mode=0o700)
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
                f"{manifest['repository']}.git",
                str(source),
            ],
            check=True,
            capture_output=True,
            env=environment,
            timeout=300,
        )
        subprocess.run(
            [
                "git",
                "-c",
                "core.hooksPath=/dev/null",
                "checkout",
                "--detach",
                manifest["buggy_revision"],
            ],
            cwd=source,
            check=True,
            capture_output=True,
            env=environment,
            timeout=120,
        )
        self._validate_identity(source, manifest)
        self.sources[identity.ordinal] = source
        prompt = self._prompt(identity, source)
        if len(prompt.encode()) > MAX_INPUT_TOKENS * 4:
            raise ValueError("provider-visible context exceeds conservative input ceiling")
        return PreparedRequest(identity, prompt, self.protocol.fairness_fingerprint)

    @staticmethod
    def _validate_identity(source: Path, manifest: dict[str, Any]) -> None:
        def git_text(*arguments: str) -> str:
            return subprocess.run(
                ["git", *arguments], cwd=source, check=True, capture_output=True, text=True
            ).stdout

        def git_bytes(*arguments: str) -> bytes:
            return subprocess.run(
                ["git", *arguments], cwd=source, check=True, capture_output=True
            ).stdout

        if git_text("rev-parse", "HEAD^{commit}").strip() != manifest["buggy_revision"]:
            raise ValueError("immutable revision mismatch")
        if git_text("rev-parse", "HEAD^{tree}").strip() != manifest["buggy_tree_identity"]:
            raise ValueError("immutable tree mismatch")
        if git_text("remote", "get-url", "origin").strip() != f"{manifest['repository']}.git":
            raise ValueError("repository identity mismatch")
        entries = git_bytes("ls-tree", "-rz", "HEAD").split(b"\0")
        if any(entry.startswith((b"120000 ", b"160000 ")) for entry in entries if entry):
            raise ValueError("symlink or gitlink rejected")
        if git_text("status", "--porcelain=v1", "--untracked-files=no"):
            raise ValueError("dirty checkout")

    def _prompt(self, identity: ExecutionIdentity, source: Path) -> str:
        selected: list[str] = []
        total = 0
        for path in sorted(source.rglob("*.py")):
            relative = path.relative_to(source).as_posix()
            if relative.startswith("tests/") or "/tests/" in relative or path.is_symlink():
                continue
            raw = path.read_bytes()
            if total + len(raw) > 100_000:
                continue
            selected.append(f"FILE {relative}\n{raw.decode('utf-8', 'replace')}")
            total += len(raw)
        additions: list[str] = []
        if identity.condition != "BASELINE":
            additions.append(self._graph_context(source, identity.ordinal))
        if identity.condition in {"GRAPH_CONSTRAINTS", "FULL_ARCHGUARD"}:
            additions.append(
                "CONSTRAINTS: preserve package boundaries, dependency direction and public APIs."
            )
        if identity.condition == "FULL_ARCHGUARD":
            additions.append(
                "ORCHESTRATION: controlled execution feedback is available only after "
                "this response."
            )
        instruction = (
            "Return only the strict archguard.repair-response/v2.1 JSON object. "
            "Do not include commands, prose, tests, fixed material, or gold material."
        )
        return "\n\n".join([TASK_TEXT[identity.task_id], instruction, *additions, *selected])

    def _graph_context(self, source: Path, ordinal: int) -> str:
        graph_root = self.root / f"run-{ordinal}" / "graph"
        graph_root.mkdir()
        snapshot, graph = graph_root / "snapshot.json", graph_root / "graph.json"
        subprocess.run(
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
            cwd=self.protocol.root,
            check=True,
            capture_output=True,
            timeout=300,
        )
        subprocess.run(
            [
                "uv",
                "run",
                "archguard",
                "graph",
                "build",
                str(snapshot),
                "--output",
                str(graph),
                "--protected-root",
                str(source),
            ],
            cwd=self.protocol.root,
            check=True,
            capture_output=True,
            timeout=300,
        )
        value = json.loads(graph.read_bytes())
        return (
            "GRAPH: "
            + json.dumps(
                {
                    "graph_fingerprint": value.get("graph_fingerprint"),
                    "nodes": value.get("nodes"),
                    "edges": value.get("edges"),
                },
                sort_keys=True,
                separators=(",", ":"),
            )[:30_000]
        )

    def process(self, request: PreparedRequest, response: bytes) -> CandidateAssessment:
        extracted = StrictRepairResponseExtractor().extract(response)
        if extracted.normalized_patch is None:
            return CandidateAssessment(
                StageStatus.FAILED,
                StageStatus.NOT_RUN,
                StageStatus.NOT_RUN,
                StageStatus.NOT_RUN,
                TerminalClassification.EXTRACTION_FAILURE,
                tuple(item.fingerprint for item in extracted.diagnostics),
            )
        source = self.sources[request.identity.ordinal]
        buggy = source.parent / "buggy"
        shutil.copytree(source, buggy, symlinks=True)
        process = subprocess.run(
            ["git", "apply", "--check", "--whitespace=error-all", "-"],
            cwd=source,
            input=extracted.normalized_patch,
            capture_output=True,
        )
        if process.returncode:
            return CandidateAssessment(
                StageStatus.PASSED,
                StageStatus.FAILED,
                StageStatus.NOT_RUN,
                StageStatus.NOT_RUN,
                TerminalClassification.APPLICATION_FAILURE,
                (diagnostic("PATCH_APPLICATION_FAILED"),),
            )
        subprocess.run(
            ["git", "apply", "--whitespace=error-all", "-"],
            cwd=source,
            input=extracted.normalized_patch,
            check=True,
            capture_output=True,
        )
        evaluation = subprocess.run(
            [
                "uv",
                "run",
                "python",
                str(self.protocol.root / "scripts/phase13_candidate_evaluator.py"),
                "--task-id",
                request.identity.task_id,
                "--buggy",
                str(buggy),
                "--candidate",
                str(source),
                "--root",
                str(self.root / f"evaluator-{request.identity.ordinal}"),
                "--repository-root",
                str(self.protocol.root),
                *(
                    ["--architecture-treatment"]
                    if request.identity.condition in {"GRAPH_CONSTRAINTS", "FULL_ARCHGUARD"}
                    else []
                ),
            ],
            cwd=self.protocol.root,
            capture_output=True,
            text=True,
            timeout=3600,
        )
        if evaluation.returncode:
            return CandidateAssessment(
                StageStatus.PASSED,
                StageStatus.PASSED,
                StageStatus.FAILED,
                StageStatus.NOT_RUN,
                TerminalClassification.INFRASTRUCTURE_FAILURE,
                (diagnostic("EVALUATOR_FAILED"),),
            )
        value = json.loads(evaluation.stdout)
        architecture_required = request.identity.condition in {
            "GRAPH_CONSTRAINTS",
            "FULL_ARCHGUARD",
        }
        architecture = StageStatus.PASSED if architecture_required else StageStatus.NOT_REQUIRED
        if value.get("architecture_status") not in {"passed", "skipped"}:
            architecture = StageStatus.FAILED
            classification = TerminalClassification.ARCHITECTURE_VIOLATION
        elif value.get("repair_success") is True:
            classification = TerminalClassification.SUCCESSFUL_REPAIR
        else:
            classification = TerminalClassification.TEST_FAILURE
        return CandidateAssessment(
            StageStatus.PASSED, StageStatus.PASSED, StageStatus.PASSED, architecture, classification
        )

    def cleanup(self) -> bool:
        containers = subprocess.run(
            ["docker", "ps", "-aq", "--filter", "label=org.archguard.phase=v2-micro-pilot"],
            capture_output=True,
            check=False,
            text=True,
        ).stdout.split()
        if containers:
            subprocess.run(["docker", "rm", "-f", *containers], capture_output=True, check=False)
        shutil.rmtree(self.root, ignore_errors=True)
        return not self.root.exists()
