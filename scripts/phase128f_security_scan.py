#!/usr/bin/env python3
"""Fail-closed, standard-library scanner for Phase 12.8F source-free evidence."""

import argparse
import json
import re
from pathlib import Path
from typing import Any

from archguard.domain.canonical import canonical_json
from archguard.domain.orchestration import fingerprint

FORBIDDEN_KEYS = {
    "fixed_code",
    "gold",
    "patch",
    "raw_log",
    "reference_patch",
    "source",
}
PATTERNS = {
    "absolute_runner_path": re.compile(r"/(?:home/runner|Users/[^/]+|private/tmp)/"),
    "diff_marker": re.compile(r"(?m)^(?:diff --git|@@ -)"),
    "private_key": re.compile(r"BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY"),
    "provider_secret": re.compile(
        r"(?:sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,})"
    ),
}


def _reject_keys(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                raise ValueError(f"forbidden evidence field: {key}")
            _reject_keys(item)
    elif isinstance(value, list):
        for item in value:
            _reject_keys(item)


def scan(paths: tuple[Path, ...]) -> dict[str, Any]:
    if not paths:
        raise ValueError("scanner requires explicit paths")
    scanned: list[str] = []
    for supplied in paths:
        if not supplied.exists():
            raise ValueError("scanner input is missing")
        files = sorted(supplied.rglob("*")) if supplied.is_dir() else [supplied]
        for path in files:
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError as error:
                raise ValueError("binary or non-UTF-8 evidence") from error
            for category, pattern in PATTERNS.items():
                if pattern.search(text):
                    raise ValueError(f"forbidden evidence pattern: {category}")
            if path.suffix == ".json":
                _reject_keys(json.loads(text))
            scanned.append(path.name)
    if not scanned:
        raise ValueError("scanner found no files")
    body: dict[str, Any] = {
        "schema": "archguard.phase-12.8f-security-scan/v1",
        "forbidden_findings": 0,
        "raw_logs_retained": False,
        "scanned_files": sorted(scanned),
        "status": "PASSED",
    }
    body["fingerprint"] = fingerprint(body)
    return body


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = scan(tuple(args.input))
    args.output.write_bytes(canonical_json(result))


if __name__ == "__main__":
    main()
