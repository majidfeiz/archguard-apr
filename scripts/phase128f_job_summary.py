#!/usr/bin/env python3
"""Write a concise source-free Phase 12.8F GitHub job summary."""

import argparse
import json
from pathlib import Path
from typing import Any

from archguard.domain.phase128f import BATCH_A, BATCH_B


def _selected(selection: str) -> tuple[str, ...]:
    if selection == "batch-a":
        return BATCH_A
    if selection == "batch-b":
        return BATCH_B
    if selection == "all":
        return BATCH_A + BATCH_B
    return (selection,)


def render(selection: str, results: list[dict[str, Any]], security: str) -> str:
    reached = {item["task_id"] for item in results}
    lines = [
        "## Phase 12.8F.4 Batch A reviewed evaluator qualification",
        "",
        "| Task | Evaluator validation | Buggy collection | Buggy scientific result | "
        "Fixed collection | Fixed result | Adapter fingerprint | Qualification decision |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for result in results:
        fixed = result.get("fixed_control") or {}
        buggy_collection = sum(
            item.get("tests_passed", 0) + item.get("tests_failed", 0)
            for item in result.get("buggy_attempts", [])
        )
        lines.append(
            f"| {result['task_id']} | {result.get('evaluator_validation_status', 'NOT_REACHED')} | "
            f"{buggy_collection} | {result.get('scientific_classification') or 'none'} | "
            f"{fixed.get('collection_count', 0)} | {fixed.get('outcome', 'NOT_REACHED')} | "
            f"{result.get('adapter_fingerprint', 'none')} | "
            f"{result.get('qualification_decision', 'NOT_QUALIFIED')} |"
        )
    not_reached = [task for task in _selected(selection) if task not in reached]
    qualified = sum(item.get("qualification_decision") == "QUALIFIED" for item in results)
    lines.extend(
        [
            "",
            f"- Executed tasks: {', '.join(sorted(reached)) or 'none'}",
            f"- Not reached after early stop: {', '.join(not_reached) or 'none'}",
            f"- Qualified count: {qualified}",
            f"- Security status: {security}",
            "- Cleanup status: verified by the always-run cleanup step",
            "- `phase_13_ready=false`",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--security-scan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    results = json.loads(args.results.read_text()) if args.results.is_file() else []
    security = "NOT_RUN"
    if args.security_scan.is_file():
        security = json.loads(args.security_scan.read_text()).get("status", "FAILED")
    with args.output.open("a", encoding="utf-8") as destination:
        destination.write(render(args.selection, results, security))


if __name__ == "__main__":
    main()
