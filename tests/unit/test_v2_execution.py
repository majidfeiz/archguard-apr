import hashlib
import json
import shutil
import zipfile
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from typer.testing import CliRunner

from archguard.application.ports.v2_execution import (
    PreparedRequest,
    Provider,
    ProviderAdmissionFailure,
    ProviderChargedFailure,
    ProviderOutcome,
)
from archguard.application.services.v2_execution import V2MicroPilotRunner
from archguard.domain.canonical import canonical_json
from archguard.domain.providers import ProviderErrorCategory, ProviderFailure
from archguard.domain.v2_execution import (
    BudgetLedger,
    ExecutionIdentity,
    ProviderFailureDiagnostic,
    ProviderFailureKind,
    frozen_identities,
)
from archguard.domain.v2_micro_pilot import SyntheticUsage
from archguard.entrypoints.cli.app import app
from archguard.infrastructure.providers.openai_responses import OpenAIResponsesAdapter
from archguard.infrastructure.providers.retry import ProviderInvocationError
from archguard.infrastructure.v2_evidence import (
    AtomicCheckpointStore,
    build_evidence_archive,
    import_evidence,
    load_checkpoint,
    validate_source_free,
)
from archguard.infrastructure.v2_protocol import load_frozen_protocol
from archguard.infrastructure.v2_runtime import (
    CapabilityProbeFailure,
    CapabilityProbeStage,
    CapabilityProbeStatus,
    DeterministicFakeProvider,
    FakePreparer,
    FakeProcessor,
    V2CapabilityProbe,
    V2OpenAIProvider,
    V2Workspace,
    safe_provider_diagnostic,
)

pytestmark = pytest.mark.unit


class RecordingCleanup:
    def __init__(self) -> None:
        self.called = False

    def cleanup(self) -> bool:
        self.called = True
        return True


def runner(
    repository_root: Path, tmp_path: Path, provider: Provider
) -> tuple[V2MicroPilotRunner, RecordingCleanup]:
    protocol = load_frozen_protocol(repository_root)
    cleanup = RecordingCleanup()
    service = V2MicroPilotRunner(
        FakePreparer(protocol.fairness_fingerprint),
        provider,
        FakeProcessor(),
        AtomicCheckpointStore(tmp_path / "checkpoint.json"),
        cleanup,
    )
    return service, cleanup


def test_exact_order_no_ninth_call_and_zero_retry(repository_root: Path, tmp_path: Path) -> None:
    provider = DeterministicFakeProvider()
    service, cleanup = runner(repository_root, tmp_path, provider)
    ledger, results, failures, cleaned = service.run()
    assert provider.calls == list(frozen_identities())
    assert [item.identity.ordinal for item in results] == list(range(1, 9))
    assert ledger.completed_calls == 8
    assert sum(item.accepted_provider_call_count for item in results) == 8
    assert failures == ()
    assert ledger.provider_request_attempts == ledger.accepted_provider_calls == 8
    assert cleanup.called and cleaned
    with pytest.raises(ValueError, match="call ceiling"):
        ledger.reserve(9)


def test_budget_admission_reconciliation_and_ceilings() -> None:
    ledger = BudgetLedger().reserve(1)
    assert ledger.reserved_cost_usd == Decimal("0.1175")
    ledger = ledger.reconcile_success(1, SyntheticUsage(35_000, 2_000))
    assert ledger.observed_cost_usd == Decimal("0.1175")
    with pytest.raises(ValueError, match="absolute"):
        replace(BudgetLedger(), observed_cost_usd=Decimal("0.90")).reserve(1)
    with pytest.raises(ValueError, match="contradictory"):
        BudgetLedger((1, 3))


def test_pre_provider_failure_is_not_a_call_and_always_cleans(
    repository_root: Path, tmp_path: Path
) -> None:
    protocol = load_frozen_protocol(repository_root)

    class FailingPreparer(FakePreparer):
        def prepare(self, identity: ExecutionIdentity):  # type: ignore[no-untyped-def]
            raise ValueError("pre-provider")

    provider = DeterministicFakeProvider()
    cleanup = RecordingCleanup()
    service = V2MicroPilotRunner(
        FailingPreparer(protocol.fairness_fingerprint),
        provider,
        FakeProcessor(),
        AtomicCheckpointStore(tmp_path / "checkpoint.json"),
        cleanup,
    )
    with pytest.raises(ValueError, match="pre-provider"):
        service.run()
    ledger, results, failures = load_checkpoint(tmp_path / "checkpoint.json")
    assert ledger.completed_calls == 0 and results == () and failures == ()
    assert provider.calls == []
    assert cleanup.called


def test_charged_failure_is_checkpointed_once_without_retry(
    repository_root: Path, tmp_path: Path
) -> None:
    calls = 0

    class ChargedProvider:
        def invoke(self, request: PreparedRequest) -> ProviderOutcome:
            nonlocal calls
            calls += 1
            raise ProviderChargedFailure(
                SyntheticUsage(100, 10),
                ProviderFailureDiagnostic(
                    ProviderFailureKind.SERVER_ERROR,
                    "response",
                    True,
                    503,
                    "overloaded",
                    True,
                    None,
                ),
            )

    service, cleanup = runner(repository_root, tmp_path, ChargedProvider())
    with pytest.raises(ProviderChargedFailure):
        service.run()
    ledger, results, failures = load_checkpoint(tmp_path / "checkpoint.json")
    assert calls == 1 and ledger.completed_ordinals == ()
    assert ledger.failed_attempt_ordinals == (1,)
    assert ledger.provider_request_attempts == ledger.accepted_provider_calls == 1
    assert results == () and len(failures) == 1
    assert cleanup.called
    with pytest.raises(ValueError, match="protocol amendment"):
        ledger.reserve(1)


def test_zero_usage_provider_rejection_is_attempt_not_call_or_scientific_completion(
    repository_root: Path, tmp_path: Path
) -> None:
    diagnostic = ProviderFailureDiagnostic(
        ProviderFailureKind.AUTHENTICATION,
        "request",
        False,
        401,
        "invalid_api_key",
        False,
        "1" * 64,
    )

    class RejectedProvider:
        def invoke(self, request: PreparedRequest) -> ProviderOutcome:
            raise ProviderAdmissionFailure(diagnostic)

    service, cleanup = runner(repository_root, tmp_path, RejectedProvider())
    with pytest.raises(ProviderAdmissionFailure):
        service.run()
    ledger, results, failures = load_checkpoint(tmp_path / "checkpoint.json")
    assert ledger.provider_request_attempts == 1
    assert ledger.accepted_provider_calls == 0
    assert ledger.completed_calls == 0
    assert ledger.infrastructure_failures == 1
    assert ledger.observed_cost_usd == 0
    assert ledger.failed_attempt_ordinals == (1,)
    assert results == ()
    assert failures[0].diagnostic == diagnostic
    assert failures[0].accepted_provider_call_count == 0
    assert cleanup.called
    with pytest.raises(ValueError, match="protocol amendment"):
        ledger.reserve(1)
    with pytest.raises(ValueError, match="positive trustworthy usage"):
        ProviderChargedFailure(SyntheticUsage(0, 0), diagnostic)


@pytest.mark.parametrize(
    ("category", "expected"),
    [
        (ProviderErrorCategory.AUTHENTICATION, ProviderFailureKind.AUTHENTICATION),
        (ProviderErrorCategory.PERMISSION, ProviderFailureKind.PERMISSION_MODEL_ACCESS),
        (ProviderErrorCategory.UNSUPPORTED_MODEL, ProviderFailureKind.PERMISSION_MODEL_ACCESS),
        (ProviderErrorCategory.INVALID_REQUEST, ProviderFailureKind.INVALID_REQUEST),
        (ProviderErrorCategory.MALFORMED_OUTPUT, ProviderFailureKind.SCHEMA_REJECTION),
        (ProviderErrorCategory.RATE_LIMITED, ProviderFailureKind.RATE_LIMIT),
        (ProviderErrorCategory.NETWORK, ProviderFailureKind.NETWORK_TRANSPORT),
        (ProviderErrorCategory.UNAVAILABLE, ProviderFailureKind.SERVER_ERROR),
        (ProviderErrorCategory.INTERNAL, ProviderFailureKind.UNKNOWN_PROVIDER_FAILURE),
    ],
)
def test_provider_failure_taxonomy_is_stable_and_source_free(
    category: ProviderErrorCategory, expected: ProviderFailureKind
) -> None:
    failure = ProviderFailure(
        category,
        category in {ProviderErrorCategory.RATE_LIMITED, ProviderErrorCategory.NETWORK},
        "secret provider text with Authorization: Bearer do-not-persist",
        "openai",
        "request",
        provider_code="safe_code",
        request_id="req_safe_123",
        http_status=429 if category is ProviderErrorCategory.RATE_LIMITED else None,
        usage_returned=False,
    )
    fake_exception = ProviderInvocationError(failure)
    value = safe_provider_diagnostic(fake_exception.failure)
    encoded = json.dumps(value.__dict__, default=str)
    assert value.kind is expected
    assert value.provider_code == "safe_code"
    assert value.request_id_hash == hashlib.sha256(b"req_safe_123").hexdigest()
    assert "secret provider text" not in encoded
    assert "Authorization" not in encoded


def test_partial_resume_never_repeats_completed_calls(
    repository_root: Path, tmp_path: Path
) -> None:
    first = DeterministicFakeProvider()

    class StopAfterThree:
        def invoke(self, request):  # type: ignore[no-untyped-def]
            if len(first.calls) == 3:
                raise ValueError("stop before fourth call")
            return first.invoke(request)

    service, _ = runner(repository_root, tmp_path, StopAfterThree())
    with pytest.raises(ValueError, match="fourth"):
        service.run()
    ledger, carried, failures = load_checkpoint(tmp_path / "checkpoint.json")
    assert ledger.completed_ordinals == (1, 2, 3)
    second = DeterministicFakeProvider()
    resumed, _ = runner(repository_root, tmp_path, second)
    final, results, final_failures, _ = resumed.run(ledger, carried, failures)
    assert [item.ordinal for item in second.calls] == [4, 5, 6, 7, 8]
    assert final.completed_calls == len(results) == 8
    assert final_failures == ()


def test_checkpoint_rejects_duplicate_and_contradictory_state(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="duplicate"):
        BudgetLedger((1, 1))
    with pytest.raises(ValueError, match="contradictory"):
        BudgetLedger((2,))
    with pytest.raises(ValueError, match="duplicate"):
        BudgetLedger(failed_attempt_ordinals=(1, 1), provider_request_attempts=2)
    with pytest.raises(ValueError, match="next scientific"):
        BudgetLedger(failed_attempt_ordinals=(2,), provider_request_attempts=1)


def test_checkpoint_rejects_tampering_and_legacy_resume_claim(
    repository_root: Path, tmp_path: Path
) -> None:
    output = tmp_path / "evidence"
    result = CliRunner().invoke(
        app,
        [
            "v2-micro-pilot",
            "dry-run",
            "--root",
            str(repository_root),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    path = output / "checkpoint.json"
    value = json.loads(path.read_bytes())
    value["ledger"]["accepted_provider_calls"] = 7
    unsigned = {key: item for key, item in value.items() if key != "fingerprint"}
    value["fingerprint"] = hashlib.sha256(canonical_json(unsigned)).hexdigest()
    path.write_bytes(canonical_json(value))
    with pytest.raises(ValueError, match="accepted provider call count"):
        load_checkpoint(path)

    value["schema"] = "archguard.v2-micro-pilot-checkpoint/v1"
    unsigned = {key: item for key, item in value.items() if key != "fingerprint"}
    value["fingerprint"] = hashlib.sha256(canonical_json(unsigned)).hexdigest()
    path.write_bytes(canonical_json(value))
    with pytest.raises(ValueError, match="schema"):
        load_checkpoint(path)


def test_resume_archive_import_rejects_contradiction_without_partial_output(
    repository_root: Path, tmp_path: Path
) -> None:
    evidence = tmp_path / "evidence"
    result = CliRunner().invoke(
        app,
        [
            "v2-micro-pilot",
            "dry-run",
            "--root",
            str(repository_root),
            "--output",
            str(evidence),
        ],
    )
    assert result.exit_code == 0, result.output
    checkpoint = evidence / "checkpoint.json"
    value = json.loads(checkpoint.read_bytes())
    value["ledger"]["completed_ordinals"] = [2, 1]
    unsigned = {key: item for key, item in value.items() if key != "fingerprint"}
    value["fingerprint"] = hashlib.sha256(canonical_json(unsigned)).hexdigest()
    checkpoint.write_bytes(canonical_json(value))
    sums = "".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
        for path in sorted(evidence.iterdir())
        if path.is_file() and path.name != "SHA256SUMS"
    )
    (evidence / "SHA256SUMS").write_text(sums)
    archive = tmp_path / "contradictory.zip"
    build_evidence_archive(evidence, archive)
    destination = tmp_path / "imported"
    destination.mkdir()
    with pytest.raises(ValueError, match="duplicate or unordered"):
        import_evidence(archive, destination)
    assert list(destination.iterdir()) == []

    duplicate = tmp_path / "duplicate.zip"
    with pytest.warns(UserWarning, match="Duplicate name"):
        with zipfile.ZipFile(duplicate, "w") as target:
            target.writestr("checkpoint.json", b"{}")
            target.writestr("checkpoint.json", b"{}")
            target.writestr("SHA256SUMS", b"")
    with pytest.raises(ValueError, match="allowlist"):
        import_evidence(duplicate, destination)


def test_deterministic_fake_end_to_end_and_flat_allowlist(
    repository_root: Path, tmp_path: Path
) -> None:
    runner_cli = CliRunner()
    one, two = tmp_path / "one", tmp_path / "two"
    archive_copies = []
    for index, destination in enumerate((one, two), 1):
        result = runner_cli.invoke(
            app,
            [
                "v2-micro-pilot",
                "dry-run",
                "--root",
                str(repository_root),
                "--output",
                str(destination),
            ],
        )
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["calls"] == 8
        copy = tmp_path / f"evidence-{index}.zip"
        shutil.copyfile(tmp_path / "v2-micro-pilot-evidence.zip", copy)
        archive_copies.append(copy)
    assert (tmp_path / "v2-micro-pilot-evidence.zip").exists()
    assert (one / "checkpoint.json").read_bytes() == (two / "checkpoint.json").read_bytes()
    assert (one / "SHA256SUMS").read_bytes() == (two / "SHA256SUMS").read_bytes()
    assert archive_copies[0].read_bytes() == archive_copies[1].read_bytes()
    imported = tmp_path / "imported"
    imported.mkdir()
    import_evidence(archive_copies[0], imported)
    assert (imported / "checkpoint.json").read_bytes() == (one / "checkpoint.json").read_bytes()


def test_offline_cli_validation_import_and_aggregation(
    repository_root: Path, tmp_path: Path
) -> None:
    cli = CliRunner()
    protocol = cli.invoke(
        app, ["v2-micro-pilot", "protocol-validate", "--root", str(repository_root)]
    )
    assert protocol.exit_code == 0 and json.loads(protocol.output)["status"] == "VALID"
    evidence = tmp_path / "evidence"
    assert (
        cli.invoke(
            app,
            [
                "v2-micro-pilot",
                "dry-run",
                "--root",
                str(repository_root),
                "--output",
                str(evidence),
            ],
        ).exit_code
        == 0
    )
    checkpoint = evidence / "checkpoint.json"
    validated = cli.invoke(app, ["v2-micro-pilot", "checkpoint-validate", str(checkpoint)])
    assert json.loads(validated.output) == {
        "accepted_provider_calls": 8,
        "completed_scientific_executions": 8,
        "failure_records": 0,
        "infrastructure_failures": 0,
        "provider_request_attempts": 8,
        "results": 8,
    }
    archive = tmp_path / "v2-micro-pilot-evidence.zip"
    assert cli.invoke(app, ["v2-micro-pilot", "evidence-validate", str(archive)]).exit_code == 0
    destination = tmp_path / "cli-import"
    assert (
        cli.invoke(
            app,
            [
                "v2-micro-pilot",
                "evidence-import",
                str(archive),
                "--destination",
                str(destination),
            ],
        ).exit_code
        == 0
    )
    aggregate = tmp_path / "aggregate.json"
    assert (
        cli.invoke(
            app,
            [
                "v2-micro-pilot",
                "aggregate",
                str(checkpoint),
                "--output",
                str(aggregate),
            ],
        ).exit_code
        == 0
    )
    assert json.loads(aggregate.read_bytes())["completed"] == 8
    refused = cli.invoke(
        app,
        [
            "v2-micro-pilot",
            "execute",
            "--root",
            str(repository_root),
            "--output",
            str(tmp_path / "real"),
            "--authorization",
            "wrong",
        ],
    )
    assert refused.exit_code == 2


def test_authorized_execute_resumes_checkpoint_without_calling_provider(
    repository_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "authorized"
    output.mkdir()
    AtomicCheckpointStore(output / "checkpoint.json").write(BudgetLedger(), (), ())
    workspace = SimpleNamespace(
        root=tmp_path / "already-clean",
        prepare=lambda identity: None,
        process=lambda request, response: None,
        cleanup=lambda: True,
    )
    monkeypatch.setattr("archguard.entrypoints.cli.v2.V2Workspace", lambda protocol: workspace)
    monkeypatch.setattr(
        "archguard.entrypoints.cli.v2.V2MicroPilotRunner.run",
        lambda self, ledger, carried, failures: (ledger, carried, failures, True),
    )
    result = CliRunner().invoke(
        app,
        [
            "v2-micro-pilot",
            "execute",
            "--root",
            str(repository_root),
            "--output",
            str(output),
            "--authorization",
            "AUTHORIZE_V2_MICRO_PILOT_8_CALLS_USD_1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"cleanup": True, "completed_calls": 0}
    assert (tmp_path / "v2-micro-pilot-evidence.zip").exists()

    inside = CliRunner().invoke(
        app,
        [
            "v2-micro-pilot",
            "execute",
            "--root",
            str(repository_root),
            "--output",
            str(repository_root / "forbidden-output"),
            "--authorization",
            "AUTHORIZE_V2_MICRO_PILOT_8_CALLS_USD_1",
        ],
    )
    assert inside.exit_code == 2


def test_real_provider_uses_existing_adapter_without_serializing_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Credential:
        configured = True

        def reveal_for_client(self) -> str:
            return "recognizable-fake-secret"

    seen: dict[str, object] = {}

    def invoke(adapter: OpenAIResponsesAdapter, prompt: str):  # type: ignore[no-untyped-def]
        seen["prompt"] = prompt
        settings = adapter.settings
        seen["reasoning_effort"] = settings.reasoning_effort
        seen["maximum_invocation_cost"] = settings.maximum_invocation_cost
        return b"{}", SimpleNamespace(input_units=12, output_units=3)

    monkeypatch.setattr(
        "archguard.infrastructure.v2_runtime.credential_for", lambda _: Credential()
    )
    monkeypatch.setattr(
        "archguard.infrastructure.v2_runtime.OpenAIResponsesAdapter.invoke_v2_repair", invoke
    )
    request = FakePreparer("f" * 64).prepare(frozen_identities()[0])
    outcome = V2OpenAIProvider().invoke(request)
    assert outcome.usage == SyntheticUsage(12, 3) and seen["prompt"] == request.prompt
    assert seen["reasoning_effort"] == "medium"
    assert seen["maximum_invocation_cost"] == "0.1175"
    assert "recognizable-fake-secret" not in repr(outcome)


def test_real_provider_preserves_safe_structured_invocation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Credential:
        configured = True

    failure = ProviderFailure(
        ProviderErrorCategory.PERMISSION,
        False,
        "raw sensitive provider body",
        "openai",
        "request",
        provider_code="model_access_denied",
        request_id="req_456",
        http_status=403,
    )

    def invoke(adapter: object, prompt: str) -> object:
        raise ProviderInvocationError(failure)

    monkeypatch.setattr(
        "archguard.infrastructure.v2_runtime.credential_for", lambda _: Credential()
    )
    monkeypatch.setattr(
        "archguard.infrastructure.v2_runtime.OpenAIResponsesAdapter.invoke_v2_repair", invoke
    )
    request = FakePreparer("f" * 64).prepare(frozen_identities()[0])
    with pytest.raises(ProviderAdmissionFailure) as raised:
        V2OpenAIProvider().invoke(request)
    encoded = json.dumps(raised.value.diagnostic.__dict__, default=str)
    assert raised.value.diagnostic.kind is ProviderFailureKind.PERMISSION_MODEL_ACCESS
    assert raised.value.diagnostic.http_status == 403
    assert "raw sensitive provider body" not in encoded


def test_capability_probe_is_one_provider_free_operational_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Credential:
        configured = True

    calls = 0

    def invoke(adapter: OpenAIResponsesAdapter, prompt: str):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        settings = adapter.settings
        assert settings.model == "gpt-5.4-2026-03-05"
        assert settings.reasoning_effort == "none"
        assert settings.retry.maximum_attempts == 1
        assert settings.maximum_invocation_cost == "0.0050"
        assert "Operational capability probe only" in prompt
        response = {
            "schema_version": "archguard.repair-response/v2.1",
            "task_id": "capability-probe",
            "candidate_id": "probe",
            "unified_diff": (
                "diff --git a/probe.py b/probe.py\n--- a/probe.py\n+++ b/probe.py\n"
                "@@ -1 +1 @@\n-old\n+new\n"
            ),
            "declared_changed_paths": ["probe.py"],
            "rationale_summary": None,
        }
        return canonical_json(response), SimpleNamespace(input_units=100, output_units=10)

    monkeypatch.setattr(
        "archguard.infrastructure.v2_runtime.credential_for", lambda _: Credential()
    )
    monkeypatch.setattr(
        "archguard.infrastructure.v2_runtime.OpenAIResponsesAdapter.invoke_v2_repair", invoke
    )
    result = V2CapabilityProbe().run()
    assert calls == 1
    assert result.provider_request_attempts == result.accepted_provider_calls == 1
    assert result.scientific_executions == 0
    assert result.status == "SUPPORTED"
    assert result.response_structure_valid and result.patch_semantics_valid
    assert Decimal(result.observed_cost_usd) <= Decimal("0.0050")


def test_probe_accepts_structure_with_invalid_patch_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "archguard.infrastructure.v2_runtime.credential_for",
        lambda _: SimpleNamespace(configured=True),
    )
    response = canonical_json(
        {
            "schema_version": "archguard.repair-response/v2.1",
            "task_id": "capability-probe",
            "candidate_id": "probe",
            "unified_diff": "not a valid patch",
            "declared_changed_paths": ["probe.py"],
            "rationale_summary": None,
        }
    )
    monkeypatch.setattr(
        "archguard.infrastructure.v2_runtime.OpenAIResponsesAdapter.invoke_v2_repair",
        lambda self, prompt: (response, SimpleNamespace(input_units=100, output_units=10)),
    )
    result = V2CapabilityProbe().run()
    assert result.status == "SUPPORTED"
    assert result.stage == "PATCH_SEMANTIC_VALIDATION"
    assert result.response_structure_valid is True
    assert result.patch_semantics_valid is False
    assert result.provider_request_attempts == result.accepted_provider_calls == 1
    assert result.scientific_executions == 0


@pytest.mark.parametrize(
    ("raw", "usage", "status", "stage"),
    [
        (
            b"{}",
            SimpleNamespace(input_units=100, output_units=10),
            "PROVIDER_ACCEPTED_RESPONSE_INVALID",
            "STRUCTURED_RESPONSE_VALIDATION",
        ),
        (
            canonical_json(
                {
                    "schema_version": "archguard.repair-response/v2.1",
                    "task_id": "probe",
                    "candidate_id": "probe",
                    "unified_diff": "invalid",
                    "declared_changed_paths": ["probe.py"],
                    "rationale_summary": None,
                }
            ),
            SimpleNamespace(input_units=1000, output_units=200),
            "PROVIDER_ACCEPTED_USAGE_INVALID",
            "USAGE_RECONCILIATION",
        ),
    ],
)
def test_probe_post_provider_failures_preserve_usage_and_counters(
    monkeypatch: pytest.MonkeyPatch,
    raw: bytes,
    usage: SimpleNamespace,
    status: str,
    stage: str,
) -> None:
    monkeypatch.setattr(
        "archguard.infrastructure.v2_runtime.credential_for",
        lambda _: SimpleNamespace(configured=True),
    )
    monkeypatch.setattr(
        "archguard.infrastructure.v2_runtime.OpenAIResponsesAdapter.invoke_v2_repair",
        lambda self, prompt: (raw, usage),
    )
    with pytest.raises(CapabilityProbeFailure) as raised:
        V2CapabilityProbe().run()
    result = raised.value.result
    assert result.status == status and result.stage == stage
    assert result.provider_request_attempts == result.accepted_provider_calls == 1
    assert result.usage_returned is True
    assert (result.input_tokens, result.output_tokens) == (usage.input_units, usage.output_units)
    assert Decimal(result.observed_cost_usd) > 0
    assert result.scientific_executions == 0


def test_probe_http_rejection_is_not_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "archguard.infrastructure.v2_runtime.credential_for",
        lambda _: SimpleNamespace(configured=True),
    )
    failure = ProviderFailure(
        ProviderErrorCategory.INVALID_REQUEST,
        False,
        "must not persist",
        "openai",
        "request",
        provider_code="invalid_request",
        http_status=400,
    )
    monkeypatch.setattr(
        "archguard.infrastructure.v2_runtime.OpenAIResponsesAdapter.invoke_v2_repair",
        lambda self, prompt: (_ for _ in ()).throw(ProviderInvocationError(failure)),
    )
    with pytest.raises(CapabilityProbeFailure) as raised:
        V2CapabilityProbe().run()
    result = raised.value.result
    assert result.status == "PROVIDER_REJECTED"
    assert result.stage == "PROVIDER_REQUEST"
    assert result.provider_request_attempts == 1
    assert result.accepted_provider_calls == result.scientific_executions == 0


def test_capability_probe_cli_requires_distinct_authorization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "probe.json"
    refused = CliRunner().invoke(
        app,
        [
            "v2-micro-pilot",
            "capability-probe",
            "--output",
            str(output),
            "--authorization",
            "AUTHORIZE_V2_MICRO_PILOT_8_CALLS_USD_1",
        ],
    )
    assert refused.exit_code == 2 and not output.exists()
    for prior_token in (
        "AUTHORIZE_V2_PROVIDER_CAPABILITY_PROBE_1_CALL",
        "AUTHORIZE_V2_PROVIDER_CAPABILITY_PROBE_SCHEMA_FIX_1_CALL",
        "AUTHORIZE_V2_PROVIDER_CAPABILITY_PROBE_REASONING_FIX_1_CALL",
    ):
        prior = CliRunner().invoke(
            app,
            [
                "v2-micro-pilot",
                "capability-probe",
                "--output",
                str(output),
                "--authorization",
                prior_token,
            ],
        )
        assert prior.exit_code == 2 and not output.exists()
    monkeypatch.setattr(
        "archguard.entrypoints.cli.v2.V2CapabilityProbe.run",
        lambda self: self._result(
            CapabilityProbeStatus.SUPPORTED,
            CapabilityProbeStage.PATCH_SEMANTIC_VALIDATION,
            attempts=1,
            accepted=1,
            usage_returned=True,
            input_tokens=100,
            output_tokens=10,
            observed_cost=Decimal("0.0004"),
            strict_schema_accepted=True,
            response_structure_valid=True,
            patch_semantics_valid=True,
            diagnostic_fingerprint="f" * 64,
        ),
    )
    accepted = CliRunner().invoke(
        app,
        [
            "v2-micro-pilot",
            "capability-probe",
            "--output",
            str(output),
            "--authorization",
            "AUTHORIZE_V2_PROVIDER_CAPABILITY_PROBE_OBSERVABILITY_FIX_1_CALL",
        ],
    )
    assert accepted.exit_code == 0
    assert json.loads(output.read_bytes())["scientific_executions"] == 0

    blocked_output = tmp_path / "blocked-probe.json"
    monkeypatch.undo()
    monkeypatch.setattr(
        "archguard.infrastructure.v2_runtime.credential_for",
        lambda _: SimpleNamespace(configured=False),
    )
    blocked = CliRunner().invoke(
        app,
        [
            "v2-micro-pilot",
            "capability-probe",
            "--output",
            str(blocked_output),
            "--authorization",
            "AUTHORIZE_V2_PROVIDER_CAPABILITY_PROBE_OBSERVABILITY_FIX_1_CALL",
        ],
    )
    assert blocked.exit_code == 3
    blocked_value = json.loads(blocked_output.read_bytes())
    assert blocked_value["status"] == "PRE_PROVIDER_BLOCKED"
    assert blocked_value["stage"] == "LOCAL_ADMISSION"
    assert blocked_value["provider_request_attempts"] == 0
    assert blocked_value["accepted_provider_calls"] == 0
    assert blocked_value["scientific_executions"] == 0


def test_second_probe_incident_record_is_source_free_and_not_accepted(
    repository_root: Path,
) -> None:
    value = json.loads(
        (repository_root / "docs/v2/v2-02b-provider-reasoning-incident.json").read_bytes()
    )
    validate_source_free(value)
    assert value["status"] == "PROVIDER_REJECTED"
    assert value["provider_request_attempts"] == 1
    assert value["accepted_provider_calls"] == value["scientific_executions"] == 0
    assert value["diagnostic"] == {
        "fingerprint": "829b6c4d5f83aa4c51081fc46ab013c34dbb4eb4874b41995a2acc5af43e1868",
        "http_status": 400,
        "kind": "INVALID_REQUEST",
        "provider_code": "unsupported_value",
        "request_id_hash": ("909519de9f104f04760dab07ded045e9da89fecdd7d2b02c840df84bf37c9f3e"),
        "retryable": False,
        "stage": "request",
        "usage_returned": False,
    }


def test_historical_observability_run_remains_ambiguous(repository_root: Path) -> None:
    value = json.loads(
        (repository_root / "docs/v2/v2-02c-probe-observability-incident.json").read_bytes()
    )
    validate_source_free(value)
    assert value["run_id"] == 46055379901
    assert value["head_sha"] == "95af0f4c3a679819319a95441f64a5d5cd108286"
    assert value["workflow_artifact_zip_sha256"] == (
        "2ae80eac5458187cef66dbf0c27e138cac14e8c971d9fc5ee0165ddf0c47b772"
    )
    assert value["historical_classification"] == "HISTORICALLY_AMBIGUOUS"
    assert value["provider_acceptance"] == "UNKNOWN"
    assert value["provider_usage"] == value["provider_cost"] == "UNKNOWN"
    assert value["scientific_executions"] == 0


def test_workspace_acquisition_context_processing_and_cleanup(
    repository_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "archguard.infrastructure.v2_runtime.os.uname",
        lambda: SimpleNamespace(sysname="Linux", machine="x86_64"),
    )
    commands: list[list[str]] = []

    def run(command: list[str], **kwargs: object) -> SimpleNamespace:
        commands.append(command)
        if "clone" in command:
            destination = Path(command[-1])
            (destination / "pysnooper").mkdir(parents=True)
            (destination / "pysnooper/tracer.py").write_text("old\n")
        if command[:5] == ["uv", "run", "archguard", "repository", "analyze"]:
            Path(command[command.index("--output") + 1]).write_text("{}")
        if command[:5] == ["uv", "run", "archguard", "graph", "build"]:
            Path(command[command.index("--output") + 1]).write_text(
                '{"graph_fingerprint":"f","nodes":[],"edges":[]}'
            )
        stdout: str | bytes = ""
        if command[:2] == ["git", "rev-parse"]:
            stdout = (
                "e21a31162f4c54be693d8ca8260e42393b39abd3\n"
                if "commit" in command[-1]
                else "999fdc6713e170e36ba077eda47294c66d2167b1\n"
            )
        elif command[:3] == ["git", "remote", "get-url"]:
            stdout = "https://github.com/cool-RR/PySnooper.git\n"
        elif command[:2] == ["git", "ls-tree"]:
            stdout = b"100644 blob deadbeef\tpysnooper/tracer.py\0"
        elif "phase13_candidate_evaluator.py" in " ".join(command):
            stdout = json.dumps({"architecture_status": "passed", "repair_success": True})
        return SimpleNamespace(returncode=0, stdout=stdout, stderr=b"")

    monkeypatch.setattr("archguard.infrastructure.v2_runtime.subprocess.run", run)
    protocol = load_frozen_protocol(repository_root)
    workspace = V2Workspace(protocol)
    baseline = workspace.prepare(frozen_identities()[0])
    graph = workspace.prepare(frozen_identities()[1])
    assert "GRAPH:" not in baseline.prompt and "GRAPH:" in graph.prompt
    response = DeterministicFakeProvider().invoke(baseline)
    assessment = workspace.process(baseline, response.response)
    assert assessment.classification.value == "SUCCESSFUL_REPAIR"
    root = workspace.root
    assert workspace.cleanup() and not root.exists()
    assert any("--no-recurse-submodules" in command for command in commands)
    assert any(command[:3] == ["docker", "ps", "-aq"] for command in commands)


def test_secret_source_gold_and_patch_leakage_is_rejected() -> None:
    for key, value in (
        ("api_key", "sk-" + "x" * 30),
        ("source_code", "print('secret')"),
        ("gold_material", "answer"),
        ("patch_body", "diff --git a/a b/a"),
        ("raw_provider_response", "payload"),
    ):
        with pytest.raises(ValueError, match="forbidden evidence field"):
            validate_source_free({key: value})


def test_protocol_and_workflow_gates(repository_root: Path) -> None:
    protocol = load_frozen_protocol(repository_root)
    assert protocol.manifest_fingerprints[0][0] == "PySnooper-2"
    path = repository_root / ".github/workflows/v2-micro-pilot.yml"
    value = yaml.safe_load(path.read_text())
    execute = value["jobs"]["execute"]
    assert execute["needs"] == "preflight"
    assert execute["environment"] == "v2-micro-pilot"
    source = path.read_text()
    assert "Execution remains blocked until readiness is true" not in source
    assert "Future execution implementation" not in source
    assert "inputs.execute_scientific_run == true" in source
    assert "AUTHORIZE_V2_MICRO_PILOT_8_CALLS_USD_1" in source
    assert "OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}" in source
    assert "if: always()" in source
    assert "actions/download-artifact@v5" in source
    assert "evidence-import" in source
    assert "resume_run_id" in source
    probe_path = repository_root / ".github/workflows/v2-provider-capability-probe.yml"
    probe_value = yaml.safe_load(probe_path.read_text())
    assert probe_value["jobs"]["probe"]["needs"] == "preflight"
    probe_source = probe_path.read_text()
    assert "AUTHORIZE_V2_PROVIDER_CAPABILITY_PROBE_OBSERVABILITY_FIX_1_CALL" in probe_source
    assert "AUTHORIZE_V2_PROVIDER_CAPABILITY_PROBE_REASONING_FIX_1_CALL'" not in probe_source
    assert "AUTHORIZE_V2_PROVIDER_CAPABILITY_PROBE_SCHEMA_FIX_1_CALL'" not in probe_source
    assert "AUTHORIZE_V2_PROVIDER_CAPABILITY_PROBE_1_CALL'" not in probe_source
    assert "environment: v2-provider-capability-probe" in probe_source
    assert "capability-probe" in probe_source
    assert "OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}" in probe_source


def test_protocol_rejects_task_identity_mismatch(repository_root: Path, tmp_path: Path) -> None:
    import shutil

    root = tmp_path / "repository"
    shutil.copytree(repository_root / "research", root / "research")
    path = root / "research/v2/manifests/pysnooper-2.json"
    value = json.loads(path.read_bytes())
    value["buggy_tree_identity"] = "0" * 40
    unsigned = {key: item for key, item in value.items() if key != "fingerprint"}
    value["fingerprint"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    ).hexdigest()
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
    with pytest.raises(ValueError, match="task manifest fingerprint mismatch"):
        load_frozen_protocol(root)
