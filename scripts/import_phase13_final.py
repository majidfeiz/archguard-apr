"""Import reviewed Phase 13 evidence and emit deterministic source-free closure artifacts."""

import argparse
import csv
from pathlib import Path
from typing import Any

from archguard.domain.canonical import canonical_json
from archguard.domain.orchestration import fingerprint
from archguard.infrastructure.phase13_final_evidence import import_final_evidence


def _write_json(path: Path, value: object) -> None:
    path.write_bytes(canonical_json(value))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    imported = import_final_evidence(arguments.archive)
    output: Path = arguments.output
    output.mkdir(parents=True, exist_ok=True)
    aggregate = imported["aggregate"]
    executions: list[dict[str, Any]] = imported["executions"]

    rows = [
        {
            "ordinal": item["run_ordinal"],
            "task_id": item["task_id"],
            "project": item["project"],
            "condition": item["condition"],
            "execution_status": "SCIENTIFIC_RESULT",
            "terminal_classification": item["terminal_classification"],
            "repair_success": item["repair_success"],
            "input_tokens": item["usage"]["input_tokens"],
            "output_tokens": item["usage"]["output_tokens"],
            "observed_usd": item["observed_usd"],
            "result_fingerprint": hashlib_sha(item),
        }
        for item in executions
    ]
    rows.extend(
        {
            "ordinal": ordinal,
            "task_id": "black-4",
            "project": "black",
            "condition": condition,
            "execution_status": "INFRASTRUCTURE_ATTRITION",
            "terminal_classification": "not_observed",
            "repair_success": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "observed_usd": "0",
            "result_fingerprint": None,
        }
        for ordinal, condition in ((5, "baseline"), (6, "archguard"))
    )
    table = {"schema": "archguard.phase-13-execution-table/v1", "rows": rows}
    table["fingerprint"] = fingerprint(table)
    pairs = {
        "schema": "archguard.phase-13-paired-table/v1",
        "rows": [
            {
                "task_id": task,
                "project": "PySnooper",
                "pair_status": "VALID_PAIRED_TASK",
                "baseline_success": False,
                "archguard_success": False,
                "discordant_success": False,
            }
            for task in ("PySnooper-2", "PySnooper-3")
        ]
        + [
            {
                "task_id": "black-4",
                "project": "black",
                "pair_status": "INFRASTRUCTURE_ATTRITION",
                "baseline_success": None,
                "archguard_success": None,
                "discordant_success": None,
            }
        ],
    }
    pairs["fingerprint"] = fingerprint(pairs)
    attrition = {
        "schema": "archguard.phase-13-attrition/v1",
        "count": 2,
        "rate": "0.3333333333333333",
        "ordinals": [5, 6],
        "task_id": "black-4",
        "classification": "PRE_PROVIDER_INFRASTRUCTURE_ATTRITION",
        "not_provider_outcomes": True,
        "not_repair_failures": True,
        "diagnostic": imported["attrition_diagnostic"],
    }
    attrition["fingerprint"] = fingerprint(attrition)
    threats = {
        "schema": "archguard.phase-13-threats-to-validity/v1",
        "study_scope": "exploratory_feasibility",
        "limitations": [
            "only_two_valid_paired_tasks",
            "one_project_represented_in_valid_results",
            "infrastructure_attrition_33.3_percent",
            "no_successful_repair",
            "patch_format_or_policy_rejection_dominated_outcomes",
            "sample_underpowered_with_zero_discordant_successful_pairs",
        ],
        "claims": {
            "generalization_supported": False,
            "superiority_supported": False,
            "confirmatory_effectiveness_evaluation": False,
            "inferential_significance_testing_performed": False,
        },
    }
    threats["fingerprint"] = fingerprint(threats)
    final_manifest = {
        "schema": "archguard.phase-13-final-manifest/v1",
        "archive_sha256": imported["archive_sha256"],
        "import_fingerprint": imported["import_fingerprint"],
        "phase_13_complete_with_attrition": True,
        "phase_13_execution_status": "COMPLETED_WITH_ATTRITION",
        "result_fingerprint": aggregate["result_fingerprint"],
        "execution_table_fingerprint": table["fingerprint"],
        "paired_table_fingerprint": pairs["fingerprint"],
        "attrition_fingerprint": attrition["fingerprint"],
        "threats_fingerprint": threats["fingerprint"],
    }
    final_manifest["fingerprint"] = fingerprint(final_manifest)
    _write_json(output / "final-manifest.json", final_manifest)
    _write_json(output / "execution-results.json", table)
    _write_json(output / "paired-task-conditions.json", pairs)
    _write_json(output / "cost-token-summary.json", aggregate)
    _write_json(output / "attrition-report.json", attrition)
    _write_json(output / "threats-to-validity.json", threats)
    _write_json(
        output / "paper-ready-results.json", {"aggregate": aggregate, "pairs": pairs["rows"]}
    )
    with (output / "paper-ready-results.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def hashlib_sha(value: object) -> str:
    import hashlib

    return hashlib.sha256(canonical_json(value)).hexdigest()


if __name__ == "__main__":
    main()
