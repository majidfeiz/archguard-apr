import hashlib
import json
import shutil
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
    ProviderChargedFailure,
    ProviderOutcome,
)
from archguard.application.services.v2_execution import V2MicroPilotRunner
from archguard.domain.v2_execution import BudgetLedger, ExecutionIdentity, frozen_identities
from archguard.domain.v2_micro_pilot import SyntheticUsage
from archguard.entrypoints.cli.app import app
from archguard.infrastructure.v2_evidence import (
    AtomicCheckpointStore,
    import_evidence,
    load_checkpoint,
    validate_source_free,
)
from archguard.infrastructure.v2_protocol import load_frozen_protocol
from archguard.infrastructure.v2_runtime import (
    DeterministicFakeProvider,
    FakePreparer,
    FakeProcessor,
    V2OpenAIProvider,
    V2Workspace,
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
    ledger, results, cleaned = service.run()
    assert provider.calls == list(frozen_identities())
    assert [item.identity.ordinal for item in results] == list(range(1, 9))
    assert ledger.completed_calls == 8
    assert sum(item.provider_call_count for item in results) == 8
    assert cleanup.called and cleaned
    with pytest.raises(ValueError, match="call ceiling"):
        ledger.reserve(9)


def test_budget_admission_reconciliation_and_ceilings() -> None:
    ledger = BudgetLedger().reserve(1)
    assert ledger.reserved_cost_usd == Decimal("0.1175")
    ledger = ledger.reconcile(1, SyntheticUsage(35_000, 2_000))
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
    ledger, results = load_checkpoint(tmp_path / "checkpoint.json")
    assert ledger.completed_calls == 0 and results == () and provider.calls == []
    assert cleanup.called


def test_charged_failure_is_checkpointed_once_without_retry(
    repository_root: Path, tmp_path: Path
) -> None:
    calls = 0

    class ChargedProvider:
        def invoke(self, request: PreparedRequest) -> ProviderOutcome:
            nonlocal calls
            calls += 1
            raise ProviderChargedFailure(SyntheticUsage(100, 10), "0" * 64)

    service, cleanup = runner(repository_root, tmp_path, ChargedProvider())
    with pytest.raises(ProviderChargedFailure):
        service.run()
    ledger, results = load_checkpoint(tmp_path / "checkpoint.json")
    assert calls == 1 and ledger.completed_ordinals == (1,)
    assert len(results) == 1 and results[0].provider_call_count == 1
    assert cleanup.called


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
    ledger, carried = load_checkpoint(tmp_path / "checkpoint.json")
    assert ledger.completed_ordinals == (1, 2, 3)
    second = DeterministicFakeProvider()
    resumed, _ = runner(repository_root, tmp_path, second)
    final, results, _ = resumed.run(ledger, carried)
    assert [item.ordinal for item in second.calls] == [4, 5, 6, 7, 8]
    assert final.completed_calls == len(results) == 8


def test_checkpoint_rejects_duplicate_and_contradictory_state(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="duplicate"):
        BudgetLedger((1, 1))
    with pytest.raises(ValueError, match="contradictory"):
        BudgetLedger((2,))


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
    assert json.loads(validated.output) == {"completed": 8, "results": 8}
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
    AtomicCheckpointStore(output / "checkpoint.json").write(BudgetLedger(), ())
    workspace = SimpleNamespace(
        root=tmp_path / "already-clean",
        prepare=lambda identity: None,
        process=lambda request, response: None,
        cleanup=lambda: True,
    )
    monkeypatch.setattr("archguard.entrypoints.cli.v2.V2Workspace", lambda protocol: workspace)
    monkeypatch.setattr(
        "archguard.entrypoints.cli.v2.V2MicroPilotRunner.run",
        lambda self, ledger, carried: (ledger, carried, True),
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

    def invoke(adapter: object, prompt: str):  # type: ignore[no-untyped-def]
        seen["prompt"] = prompt
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
    assert "recognizable-fake-secret" not in repr(outcome)


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
    assert "exit 2" not in source
    assert "inputs.execute_scientific_run == true" in source
    assert "AUTHORIZE_V2_MICRO_PILOT_8_CALLS_USD_1" in source
    assert "OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}" in source
    assert "if: always()" in source


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
