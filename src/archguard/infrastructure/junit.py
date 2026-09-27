"""Bounded pytest/JUnit observations without console-text inference."""

import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath, PureWindowsPath

from archguard.domain.execution import TestCaseObservation, TestState
from archguard.infrastructure.artifact_io import read_artifact

MAX_JUNIT_BYTES = 8 * 1024 * 1024


def _test_id(case: ET.Element) -> str:
    classname = case.get("classname", "").replace("\\", "/").strip("/")
    raw_file = case.get("file", "").replace("\\", "/")
    file_name = raw_file.strip("/")
    name = case.get("name", "")
    if not name or "\x00" in name:
        raise ValueError("invalid JUnit test identity")
    if file_name:
        path = PurePosixPath(file_name)
        if path.is_absolute() or PureWindowsPath(case.get("file", "")).anchor or ".." in path.parts:
            file_name = path.name
    prefix = file_name or classname or "test"
    return f"{prefix}::{name}"


def parse_junit(path: Path) -> tuple[TestCaseObservation, ...]:
    raw = read_artifact(path, None, MAX_JUNIT_BYTES)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        raise ValueError("malformed JUnit report") from None
    results: list[TestCaseObservation] = []
    seen: set[str] = set()
    for case in root.iter("testcase"):
        test_id = _test_id(case)
        if test_id in seen:
            raise ValueError("duplicate JUnit test identity")
        seen.add(test_id)
        if case.find("failure") is not None:
            state = TestState.FAILED
        elif case.find("error") is not None:
            state = TestState.ERROR
        elif (skipped := case.find("skipped")) is not None:
            kind = (skipped.get("type", "") + skipped.get("message", "")).lower()
            state = TestState.XFAIL if "xfail" in kind else TestState.SKIPPED
        elif case.get("status", "").lower() == "xpass":
            state = TestState.XPASS
        else:
            state = TestState.PASSED
        results.append(TestCaseObservation(test_id, state))
    if not results:
        raise ValueError("JUnit report contains zero tests")
    return tuple(sorted(results))
