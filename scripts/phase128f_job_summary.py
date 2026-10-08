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
        "## Phase 12.8F.3 Batch A execution-path verification",
        "",
        "| Task | Buggy status | Fixed status | Fixed stage | Fixed failure category | "
        "Source identity match | Qualification decision |",
        "|---|---|---|---|---|---|---|",
    ]
    for result in results:
        fixed = result.get("fixed_control") or {}
        source_identity = fixed.get("source_identity") or {}
        source_match = bool(source_identity) and (
            source_identity.get("working_directory_fingerprint")
            == source_identity.get("container_visible_source_fingerprint")
        )
        lines.append(
            f"| {result['task_id']} | {result.get('buggy_result_status', 'NOT_REACHED')} | "
            f"{fixed.get('outcome', 'NOT_REACHED')} | {fixed.get('stage', 'none')} | "
            f"{fixed.get('normalized_failure_class') or 'none'} | {str(source_match).lower()} | "
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
