import csv
import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from archguard.domain.canonical import canonical_json
from archguard.domain.phase13_results import aggregate_phase13_results
from archguard.infrastructure.phase13_final_evidence import (
    DIAGNOSTIC_FINGERPRINT,
    POPULATION_FINGERPRINT,
    PROTOCOL_FINGERPRINT,
    PROVIDER_FINGERPRINT,
    import_final_evidence,
)


def _executions() -> list[dict[str, object]]:
    return [
        {
            "run_ordinal": 1,
            "condition": "baseline",
            "terminal_classification": "invalid_patch",
            "repair_success": False,
            "observed_usd": "0.025945",
            "usage": {
                "input_tokens": 5200,
                "output_tokens": 863,
                "cached_input_tokens": 0,
                "reasoning_tokens": 0,
            },
        },
        {
            "run_ordinal": 2,
            "condition": "archguard",
            "terminal_classification": "invalid_patch",
            "repair_success": False,
            "observed_usd": "0.06102",
            "usage": {
                "input_tokens": 15108,
                "output_tokens": 1550,
                "cached_input_tokens": 0,
                "reasoning_tokens": 0,
            },
        },
        {
            "run_ordinal": 3,
            "condition": "baseline",
            "terminal_classification": "invalid_patch",
            "repair_success": False,
            "observed_usd": "0.0091625",
            "usage": {
                "input_tokens": 2621,
                "output_tokens": 174,
                "cached_input_tokens": 0,
                "reasoning_tokens": 0,
            },
        },
        {
            "run_ordinal": 4,
            "condition": "archguard",
            "terminal_classification": "invalid_patch",
            "repair_success": False,
            "observed_usd": "0.033505",
            "usage": {
                "input_tokens": 12502,
                "output_tokens": 150,
                "cached_input_tokens": 0,
                "reasoning_tokens": 0,
            },
        },
    ]


def test_phase13_aggregation_is_descriptive_exact_and_deterministic() -> None:
    first = aggregate_phase13_results(_executions())
    assert first == aggregate_phase13_results(_executions())
    assert first["phase_13_execution_status"] == "COMPLETED_WITH_ATTRITION"
    assert first["completed_executions"] == 4
    assert first["infrastructure_attrition"] == 2
    assert first["valid_paired_tasks"] == 2
    assert first["repair_successes"] == 0
    assert first["invalid_patches"] == 4
    assert first["observed_usd"] == "0.1296325"
    assert first["input_tokens"] == 35431
    assert first["output_tokens"] == 2737
    assert first["conditions"]["archguard"]["observed_usd"] == "0.094525"
    assert first["conditions"]["baseline"]["observed_usd"] == "0.0351075"
    assert first["inferential_testing"] == "not_performed_underpowered_zero_discordant_pairs"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda values: values.reverse(),
        lambda values: values[0].update(terminal_classification="success"),
        lambda values: values[0].update(repair_success=True),
        lambda values: values[0].update(condition="archguard"),
    ],
)
def test_phase13_aggregation_fails_closed(mutation: object) -> None:
    values = _executions()
    assert callable(mutation)
    mutation(values)
    with pytest.raises(ValueError):
        aggregate_phase13_results(values)


def test_committed_closure_artifacts_are_canonical_and_do_not_overclaim(
    repository_root: Path,
) -> None:
    root = repository_root / "research/results/phase-13"
    for path in root.glob("*.json"):
        value = json.loads(path.read_bytes())
        assert path.read_bytes() == canonical_json(value)
    threats = json.loads((root / "threats-to-validity.json").read_text())
    assert threats["claims"] == {
        "confirmatory_effectiveness_evaluation": False,
        "generalization_supported": False,
        "inferential_significance_testing_performed": False,
        "superiority_supported": False,
    }
    rows = list(csv.DictReader((root / "paper-ready-results.csv").open()))
    assert len(rows) == 6
    assert [row["execution_status"] for row in rows[4:]] == [
        "INFRASTRUCTURE_ATTRITION",
        "INFRASTRUCTURE_ATTRITION",
    ]


def test_final_import_rejects_unreviewed_archive(tmp_path: Path) -> None:
    archive = tmp_path / "unreviewed.zip"
    archive.write_bytes(b"not reviewed evidence")
    with pytest.raises(ValueError, match="identity mismatch"):
        import_final_evidence(archive)


def test_final_import_accepts_exact_source_free_contract(
    repository_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkpoint = json.loads(
        (repository_root / "research/evidence/phase-13-checkpoint-four-executions.json").read_text()
    )
    executions = checkpoint["completed_executions"]
    result_fingerprints = [
        hashlib.sha256(
            canonical_json({key: value for key, value in item.items() if key != "provider_call_id"})
        ).hexdigest()
        for item in executions
    ]
    members: dict[str, object] = {
        "home/runner/work/_temp/provider-preflight.json": {},
        "home/runner/work/_temp/checkpoint.json": {},
        "tmp/archguard-phase13-cost-state.json": {},
        "tmp/archguard-phase13-evidence/cleanup.json": {
            "complete": True,
            "schema": "archguard.phase-13-cleanup/v1",
        },
        "tmp/archguard-phase13-evidence/cost-state.json": {
            "provider_calls_completed": 4,
            "observed_usd": "0.1296325",
            "reserved_usd": "0",
            "remaining_internal_budget_usd": "4.3703675",
        },
        "tmp/archguard-phase13-evidence/manifest.json": {
            "completed_executions": 4,
            "attrition": 2,
            "result_fingerprints": result_fingerprints,
            "population_fingerprint": POPULATION_FINGERPRINT,
            "protocol_fingerprint": PROTOCOL_FINGERPRINT,
            "provider_configuration_fingerprint": PROVIDER_FINGERPRINT,
        },
        "tmp/archguard-phase13-evidence/pre-provider-failure.json": {
            "stage": "checkout",
            "exception_category": "validation_failure",
            "diagnostic_fingerprint": DIAGNOSTIC_FINGERPRINT,
        },
    }
    for ordinal, execution in enumerate(executions, start=1):
        members[f"tmp/archguard-phase13-evidence/execution-{ordinal}.json"] = execution
    archive = tmp_path / "final.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for name, value in members.items():
            bundle.writestr(name, canonical_json(value))
    archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    monkeypatch.setattr(
        "archguard.infrastructure.phase13_final_evidence.ARCHIVE_SHA256", archive_hash
    )
    imported = import_final_evidence(archive)
    assert imported["archive_sha256"] == archive_hash
    assert imported["aggregate"]["completed_ordinals"] == [1, 2, 3, 4]
    assert imported["aggregate"]["infrastructure_attrition"] == 2
