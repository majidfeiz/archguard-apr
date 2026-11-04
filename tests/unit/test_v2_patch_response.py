import builtins
import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from unittest.mock import patch

import pytest

from archguard.application.services.v2_patch import ExtractRepairResponse
from archguard.domain.v2_patch import (
    PATCH_DIAGNOSTIC_SCHEMA,
    REPAIR_RESPONSE_SCHEMA,
    ExtractedPatch,
    PatchStage,
    V2PatchDiagnostic,
    V2PatchDiagnosticCode,
)
from archguard.infrastructure.v2_patch_response import StrictRepairResponseExtractor

pytestmark = pytest.mark.unit


def fixture(root: Path, name: str) -> bytes:
    return (root / "tests/fixtures/v2_patch" / name).read_bytes()


def code(result: ExtractedPatch) -> V2PatchDiagnosticCode:
    return result.diagnostics[0].code


def structured(diff: bytes, paths: list[str] | None = None, **extra: object) -> bytes:
    value = {
        "schema_version": REPAIR_RESPONSE_SCHEMA,
        "task_id": "synthetic-task",
        "candidate_id": "candidate-1",
        "unified_diff": diff.decode(),
        "declared_changed_paths": paths or ["src/demo.py"],
        **extra,
    }
    return json.dumps(value, sort_keys=True).encode()


def test_raw_fenced_and_structured_forms_are_deterministic(repository_root: Path) -> None:
    extractor = StrictRepairResponseExtractor()
    raw = fixture(repository_root, "valid.diff")
    values = [
        extractor.extract(raw),
        extractor.extract(fixture(repository_root, "valid-fenced.txt")),
        extractor.extract(structured(raw)),
    ]
    assert [item.input_format for item in values] == ["raw_diff", "markdown_fence", "structured"]
    assert len({item.normalized_patch_sha256 for item in values}) == 1
    assert values[0] == extractor.extract(raw)
    assert values[2].declared_changed_paths == ("src/demo.py",)
    evidence = values[2].source_free_evidence()
    assert "normalized_patch" not in evidence
    assert b"VALUE = 2" not in json.dumps(evidence).encode()
    assert values[0].raw_input_sha256 == hashlib.sha256(raw).hexdigest()
    assert ExtractRepairResponse(extractor).execute(raw) == values[0]


def test_crlf_is_the_only_patch_presentation_normalization(repository_root: Path) -> None:
    raw = fixture(repository_root, "valid.diff")
    crlf = raw.replace(b"\n", b"\r\n")
    result = StrictRepairResponseExtractor().extract(crlf)
    assert result.normalized_patch == raw
    assert result.raw_input_sha256 != result.normalized_patch_sha256


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("prose-only.txt", V2PatchDiagnosticCode.NO_PATCH_FOUND),
        ("truncated.diff", V2PatchDiagnosticCode.TRUNCATED_DIFF),
        ("path-traversal.diff", V2PatchDiagnosticCode.UNSAFE_PATH),
        ("rename.diff", V2PatchDiagnosticCode.UNSUPPORTED_PATCH_OPERATION),
        ("binary.diff", V2PatchDiagnosticCode.UNSUPPORTED_PATCH_OPERATION),
        ("symlink.diff", V2PatchDiagnosticCode.UNSUPPORTED_PATCH_OPERATION),
        ("absolute-path.diff", V2PatchDiagnosticCode.UNSAFE_PATH),
        ("malformed.diff", V2PatchDiagnosticCode.MALFORMED_DIFF_HEADER),
        ("no-op.diff", V2PatchDiagnosticCode.NO_EFFECTIVE_CHANGE),
        ("multiple.txt", V2PatchDiagnosticCode.MULTIPLE_PATCHES_FOUND),
    ],
)
def test_synthetic_rejections(
    repository_root: Path, name: str, expected: V2PatchDiagnosticCode
) -> None:
    result = StrictRepairResponseExtractor().extract(fixture(repository_root, name))
    assert code(result) == expected
    assert result.normalized_patch is None


def test_multiple_and_ambiguous_candidates_fail_closed(repository_root: Path) -> None:
    raw = fixture(repository_root, "valid.diff")
    extractor = StrictRepairResponseExtractor()
    assert code(extractor.extract(b"prefix\n" + raw)) == V2PatchDiagnosticCode.AMBIGUOUS_RESPONSE
    assert code(extractor.extract(raw + raw)) == V2PatchDiagnosticCode.MULTIPLE_PATCHES_FOUND


@pytest.mark.parametrize(
    "mutator",
    [
        lambda value: {**value, "command": "pytest"},
        lambda value: {**value, "schema_version": "wrong"},
        lambda value: {key: item for key, item in value.items() if key != "candidate_id"},
        lambda value: {**value, "declared_changed_paths": ["../secret"]},
        lambda value: {**value, "task_id": " task"},
    ],
)
def test_strict_schema_rejects_unknown_missing_and_unsafe_fields(
    repository_root: Path, mutator: Callable[[dict[str, object]], dict[str, object]]
) -> None:
    raw = fixture(repository_root, "valid.diff")
    value = json.loads(structured(raw))
    changed = mutator(value)
    result = StrictRepairResponseExtractor().extract(json.dumps(changed).encode())
    assert code(result) == V2PatchDiagnosticCode.RESPONSE_SCHEMA_INVALID


def test_declared_paths_must_exactly_match(repository_root: Path) -> None:
    raw = fixture(repository_root, "valid.diff")
    result = StrictRepairResponseExtractor().extract(structured(raw, ["src/other.py"]))
    assert code(result) == V2PatchDiagnosticCode.DECLARED_PATH_MISMATCH
    assert result.diagnostics[0].stage == PatchStage.POLICY_VALIDATION


def test_parser_never_executes_or_imports_candidate_content(repository_root: Path) -> None:
    raw = fixture(repository_root, "valid.diff").replace(
        b"VALUE = 2", b"__import__('os').system('x')"
    )
    raw = raw.replace(b"@@ -1 +1 @@", b"@@ -1 +1 @@")
    original_import = builtins.__import__

    def reject_candidate_import(
        name: str,
        globals: Mapping[str, object] | None = None,
        locals: Mapping[str, object] | None = None,
        fromlist: Sequence[str] = (),
        level: int = 0,
    ) -> object:
        if name == "os":
            raise AssertionError("candidate import called")
        return original_import(name, globals, locals, fromlist, level)

    with (
        patch("builtins.eval", side_effect=AssertionError("eval called")),
        patch("builtins.exec", side_effect=AssertionError("exec called")),
        patch("builtins.__import__", side_effect=reject_candidate_import),
    ):
        result = StrictRepairResponseExtractor().extract(raw)
    assert result.normalized_patch is not None


def test_diagnostic_fingerprint_is_stable_and_source_free() -> None:
    first = V2PatchDiagnostic.create(
        PatchStage.PATCH_EXTRACTION, V2PatchDiagnosticCode.NO_PATCH_FOUND
    )
    second = V2PatchDiagnostic.create(
        PatchStage.PATCH_EXTRACTION, V2PatchDiagnosticCode.NO_PATCH_FOUND
    )
    assert first == second
    assert len(first.fingerprint) == 64
    assert PATCH_DIAGNOSTIC_SCHEMA == "archguard.patch-diagnostic/v2.1"


def test_invalid_utf8_duplicate_json_and_oversize_fail_closed(repository_root: Path) -> None:
    extractor = StrictRepairResponseExtractor()
    assert code(extractor.extract(b"\xff")) == V2PatchDiagnosticCode.RESPONSE_SCHEMA_INVALID
    duplicate = b'{"schema_version":"x","schema_version":"y"}'
    assert code(extractor.extract(duplicate)) == V2PatchDiagnosticCode.RESPONSE_SCHEMA_INVALID
    assert code(extractor.extract(fixture(repository_root, "empty-response.json"))) == (
        V2PatchDiagnosticCode.RESPONSE_SCHEMA_INVALID
    )
    oversized = fixture(repository_root, "valid.diff") + b"x" * (4 * 1024 * 1024 + 16 * 1024)
    assert code(extractor.extract(oversized)) == V2PatchDiagnosticCode.PATCH_TOO_LARGE
