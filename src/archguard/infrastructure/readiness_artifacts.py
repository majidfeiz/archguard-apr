"""Strict JSON adapters for Phase 12.8 human decisions and readiness facts."""

import json
from pathlib import Path
from typing import Any

from archguard.domain.readiness import HumanDecision, HumanDecisionRecord
from archguard.infrastructure.artifact_io import read_artifact


def load_json(path: Path) -> dict[str, Any]:
    raw = read_artifact(path, None, 1024 * 1024)
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("artifact must be an object")
    return value


def load_human_decision(path: Path) -> HumanDecisionRecord:
    value = load_json(path)
    expected = {
        "schema",
        "subject_kind",
        "reviewed_fingerprint",
        "reviewer_name",
        "review_timestamp",
        "decision",
        "checklist",
        "comments",
    }
    if (
        set(value) != expected
        or not isinstance(value["checklist"], dict)
        or not all(isinstance(item, bool) for item in value["checklist"].values())
    ):
        raise ValueError("invalid human decision fields")
    return HumanDecisionRecord(
        schema=str(value["schema"]),
        subject_kind=str(value["subject_kind"]),
        reviewed_fingerprint=str(value["reviewed_fingerprint"]),
        reviewer_name=str(value["reviewer_name"]),
        review_timestamp=str(value["review_timestamp"]),
        decision=HumanDecision(str(value["decision"])),
        checklist={str(k): v for k, v in value["checklist"].items()},
        comments=str(value["comments"]),
    )
