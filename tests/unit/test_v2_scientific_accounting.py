import hashlib
import io
import json
import zipfile
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from typer.testing import CliRunner

from archguard.application.ports.v2_execution import (
    ProviderAdmissionFailure,
    ProviderChargedFailure,
    ProviderOutcome,
)
from archguard.application.services.v2_execution import V2MicroPilotRunner
from archguard.domain.canonical import canonical_json
from archguard.domain.providers import (
    ProviderErrorCategory,
    ProviderFailure,
    ProviderResponseState,
    ProviderUsage,
)
from archguard.domain.v2_execution import TerminalClassification, frozen_identities
from archguard.domain.v2_micro_pilot import SyntheticUsage
from archguard.entrypoints.cli.app import app
from archguard.infrastructure.providers.retry import ProviderInvocationError
from archguard.infrastructure.v2_evidence import AtomicCheckpointStore, load_checkpoint
from archguard.infrastructure.v2_runtime import (
    FakePreparer,
    FakeProcessor,
    NoopCleanup,
    V2OpenAIProvider,
)
from archguard.infrastructure.v2_scientific_history import (
    JSON_MEMBERS,
    PREFLIGHT_MEMBER,
    import_scientific_history,
    validate_frozen_scientific_history,
    validate_scientific_archives,
)

pytestmark = pytest.mark.unit


def _zip(members: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, raw in sorted(members.items()):
            archive.writestr(name, raw)
    return output.getvalue()


def _artifacts(root: Path) -> tuple[bytes, bytes]:
    directory = root / "research/v2/evidence/scientific-run-1"
    evidence = {name: (directory / name).read_bytes() for name in JSON_MEMBERS}
    sums = "".join(
        f"{hashlib.sha256(raw).hexdigest()}  {name}\n" for name, raw in sorted(evidence.items())
    ).encode()
    inner = _zip({"SHA256SUMS": sums, **evidence})
    outer = _zip(
        {
            **{f"archguard-v2-evidence/{name}": raw for name, raw in evidence.items()},
            "archguard-v2-evidence/SHA256SUMS": sums,
            "v2-micro-pilot-evidence.zip": inner,
        }
    )
    preflight = _zip(
        {
            PREFLIGHT_MEMBER: (
                root / "research/v2/readiness/amended-micro-pilot-readiness.json"
            ).read_bytes()
        }
    )
    return outer, preflight


def test_archives_validate_and_import_exactly(
    repository_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outer, preflight = _artifacts(repository_root)
    monkeypatch.setattr(
        "archguard.infrastructure.v2_scientific_history.SOURCE_ARTIFACT_SHA256",
        hashlib.sha256(outer).hexdigest(),
    )
    monkeypatch.setattr(
        "archguard.infrastructure.v2_scientific_history.PREFLIGHT_ARTIFACT_SHA256",
        hashlib.sha256(preflight).hexdigest(),
    )
    source_path, preflight_path = tmp_path / "source.zip", tmp_path / "preflight.zip"
    source_path.write_bytes(outer)
    preflight_path.write_bytes(preflight)
    imported = validate_scientific_archives(source_path, preflight_path)
    destination = tmp_path / "imported"
    import_scientific_history(source_path, preflight_path, destination)
    import_scientific_history(source_path, preflight_path, destination)
    assert {path.name: path.read_bytes() for path in destination.iterdir()} == imported
    source_path.write_bytes(outer + b"tamper")
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_scientific_archives(source_path, preflight_path)


def test_archive_validation_rejects_structure_and_import_contradictions(
    repository_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outer, preflight = _artifacts(repository_root)
    source_path, preflight_path = tmp_path / "source.zip", tmp_path / "preflight.zip"
    source_path.write_bytes(outer)
    preflight_path.write_bytes(preflight)
    monkeypatch.setattr(
        "archguard.infrastructure.v2_scientific_history.SOURCE_ARTIFACT_SHA256",
        hashlib.sha256(outer).hexdigest(),
    )
    monkeypatch.setattr(
        "archguard.infrastructure.v2_scientific_history.PREFLIGHT_ARTIFACT_SHA256",
        hashlib.sha256(preflight).hexdigest(),
    )
    destination = tmp_path / "imported"
    import_scientific_history(source_path, preflight_path, destination)
    checkpoint = destination / "checkpoint.json"
    checkpoint.chmod(0o644)
    checkpoint.write_bytes(b"{}\n")
    with pytest.raises(ValueError, match="contradicts"):
        import_scientific_history(source_path, preflight_path, destination)

    wrong = _zip({"unexpected.json": b"{}\n"})
    source_path.write_bytes(wrong)
    monkeypatch.setattr(
        "archguard.infrastructure.v2_scientific_history.SOURCE_ARTIFACT_SHA256",
        hashlib.sha256(wrong).hexdigest(),
    )
    with pytest.raises(ValueError, match="membership mismatch"):
        validate_scientific_archives(source_path, preflight_path)


def test_frozen_history_cli_and_error_contracts(repository_root: Path) -> None:
    result = CliRunner().invoke(
        app,
        ["v2-micro-pilot", "scientific-history-validate", "--root", str(repository_root)],
    )
    assert result.exit_code == 0 and result.output.strip() == "VALID"
    failure = ProviderFailure(
        ProviderErrorCategory.INCOMPLETE,
        False,
        "safe",
        "openai",
        "response",
    )
    usage = ProviderUsage(1, 1, None, None, "openai", "model")
    with pytest.raises(ValueError, match="not marked returned"):
        ProviderInvocationError(failure, usage)
    returned = ProviderFailure(
        ProviderErrorCategory.INCOMPLETE,
        False,
        "safe",
        "openai",
        "response",
        usage_returned=True,
    )
    with pytest.raises(ValueError, match="requires trustworthy"):
        ProviderInvocationError(returned, response_state=ProviderResponseState.INCOMPLETE_OTHER)


def test_frozen_history_and_proposal_are_authoritative(repository_root: Path) -> None:
    validate_frozen_scientific_history(repository_root)
    checkpoint = repository_root / "research/v2/evidence/scientific-run-1/checkpoint.json"
    ledger, results, failures = load_checkpoint(checkpoint)
    assert ledger.provider_request_attempts == 2
    assert ledger.accepted_provider_calls == ledger.completed_calls == 1
    assert ledger.observed_cost_usd == Decimal("0.0432275")
    assert results[0].terminal_classification is TerminalClassification.EXTRACTION_FAILURE
    assert failures[0].diagnostic.usage_returned is True
    assert failures[0].accepted_provider_call_count == 0
    proposal_path = (
        repository_root / "research/v2/protocol/scientific-continuation-proposal-v1.json"
    )
    proposal = json.loads(proposal_path.read_bytes())
    fingerprint = proposal.pop("fingerprint")
    assert fingerprint == hashlib.sha256(canonical_json(proposal)).hexdigest()
    assert proposal["ordinal_2_rerun_permitted"] is False
    assert proposal["continuation_ordinals"] == [3, 4, 5, 6, 7, 8]


def test_usage_bearing_schema_failure_is_accepted_and_reconciled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "archguard.infrastructure.v2_runtime.credential_for",
        lambda _: SimpleNamespace(configured=True),
    )
    failure = ProviderFailure(
        ProviderErrorCategory.MALFORMED_OUTPUT,
        False,
        "safe",
        "openai",
        "response",
        usage_returned=True,
    )
    usage = ProviderUsage(5291, 2000, None, None, "openai", "gpt-5.4-2026-03-05")
    monkeypatch.setattr(
        "archguard.infrastructure.v2_runtime.OpenAIResponsesAdapter.invoke_v2_repair",
        lambda self, prompt: (_ for _ in ()).throw(
            ProviderInvocationError(failure, usage, ProviderResponseState.SCHEMA_REJECTION)
        ),
    )
    service = V2MicroPilotRunner(
        FakePreparer("f" * 64),
        V2OpenAIProvider(),
        FakeProcessor(),
        AtomicCheckpointStore(tmp_path / "checkpoint.json"),
        NoopCleanup(),
    )
    with pytest.raises(ProviderChargedFailure):
        service.run()
    ledger, results, failures = load_checkpoint(tmp_path / "checkpoint.json")
    assert results == () and ledger.completed_calls == 0
    assert ledger.provider_request_attempts == ledger.accepted_provider_calls == 1
    assert ledger.observed_cost_usd == SyntheticUsage(5291, 2000).cost
    assert failures[0].response_state is ProviderResponseState.SCHEMA_REJECTION
    assert (failures[0].input_tokens, failures[0].output_tokens) == (5291, 2000)
    with pytest.raises(ValueError, match="protocol amendment"):
        ledger.reserve(1)


def test_untrustworthy_returned_usage_fails_without_fabricated_accounting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "archguard.infrastructure.v2_runtime.credential_for",
        lambda _: SimpleNamespace(configured=True),
    )
    failure = ProviderFailure(
        ProviderErrorCategory.MALFORMED_OUTPUT,
        False,
        "safe",
        "openai",
        "response",
        usage_returned=True,
    )
    invalid = SimpleNamespace(input_units=-1, output_units=2)
    monkeypatch.setattr(
        "archguard.infrastructure.v2_runtime.OpenAIResponsesAdapter.invoke_v2_repair",
        lambda self, prompt: (_ for _ in ()).throw(
            ProviderInvocationError(
                failure,
                cast(ProviderUsage, invalid),
                ProviderResponseState.SCHEMA_REJECTION,
            )
        ),
    )
    request = FakePreparer("f" * 64).prepare(frozen_identities()[0])
    with pytest.raises(ProviderAdmissionFailure) as raised:
        V2OpenAIProvider().invoke(request)
    assert raised.value.diagnostic.provider_code == "invalid_usage"

    monkeypatch.setattr(
        "archguard.infrastructure.v2_runtime.OpenAIResponsesAdapter.invoke_v2_repair",
        lambda self, prompt: (b"{}", cast(ProviderUsage, invalid)),
    )
    with pytest.raises(ProviderAdmissionFailure) as returned:
        V2OpenAIProvider().invoke(request)
    assert returned.value.diagnostic.stage == "usage_validation"


def test_extraction_failure_remains_completed_scientific_execution(tmp_path: Path) -> None:
    class InvalidPatchProvider:
        def invoke(self, request: object) -> ProviderOutcome:
            return ProviderOutcome(b"{}", SyntheticUsage(100, 10))

    service = V2MicroPilotRunner(
        FakePreparer("f" * 64),
        InvalidPatchProvider(),
        FakeProcessor(),
        AtomicCheckpointStore(tmp_path / "checkpoint.json"),
        NoopCleanup(),
    )
    ledger, results, failures, _ = service.run()
    assert ledger.completed_calls == 8 and failures == ()
    assert all(
        result.terminal_classification is TerminalClassification.EXTRACTION_FAILURE
        for result in results
    )
    assert all(result.response_state is ProviderResponseState.COMPLETED for result in results)
