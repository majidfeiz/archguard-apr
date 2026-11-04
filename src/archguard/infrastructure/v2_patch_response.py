"""Deterministic extraction before the existing strict unified-diff inspector."""

import hashlib
import json
import re
from typing import Any, cast

from archguard.domain.patch_validation import PatchDiagnostic, PatchDiagnosticCode
from archguard.domain.v2_patch import (
    MAX_PATCH_FILES,
    MAX_PATCH_HUNKS,
    MAX_PATCH_LINES,
    MAX_RESPONSE_BYTES,
    PATCH_DIAGNOSTIC_SCHEMA,
    REPAIR_RESPONSE_SCHEMA,
    ExtractedPatch,
    PatchStage,
    RepairResponse,
    V2PatchDiagnostic,
    V2PatchDiagnosticCode,
)
from archguard.infrastructure.json_codec import unique_object
from archguard.infrastructure.patch_inspector import UnifiedDiffInspector

FENCE = re.compile(rb"\A```(?:diff|patch)?[ \t]*\r?\n(.*)\r?\n```[ \t]*\r?\n?\Z", re.DOTALL)
DIFF_START = b"diff --git "
ALLOWED_FIELDS = {
    "schema_version",
    "task_id",
    "candidate_id",
    "unified_diff",
    "declared_changed_paths",
    "rationale_summary",
}


class StrictRepairResponseExtractor:
    def __init__(self, inspector: UnifiedDiffInspector | None = None) -> None:
        self._inspector = inspector or UnifiedDiffInspector()

    def extract(self, raw: bytes) -> ExtractedPatch:
        raw_hash = hashlib.sha256(raw).hexdigest()
        if len(raw) > MAX_RESPONSE_BYTES:
            return self._reject(
                raw_hash, PatchStage.PATCH_EXTRACTION, V2PatchDiagnosticCode.PATCH_TOO_LARGE
            )
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return self._reject(
                raw_hash, PatchStage.RESPONSE_PARSING, V2PatchDiagnosticCode.RESPONSE_SCHEMA_INVALID
            )
        stripped = text.strip()
        declared: tuple[str, ...] = ()
        form = "raw_diff"
        patch: bytes
        if stripped.startswith("{"):
            form = "structured"
            try:
                data = json.loads(text, object_pairs_hook=unique_object)
                response = self._structured(data)
            except (TypeError, ValueError):
                return self._reject(
                    raw_hash,
                    PatchStage.RESPONSE_PARSING,
                    V2PatchDiagnosticCode.RESPONSE_SCHEMA_INVALID,
                )
            declared = response.declared_changed_paths
            patch = response.unified_diff.encode("utf-8")
        else:
            if raw.count(b"```diff") > 1 or raw.count(b"```patch") > 1:
                return self._reject(
                    raw_hash,
                    PatchStage.PATCH_EXTRACTION,
                    V2PatchDiagnosticCode.MULTIPLE_PATCHES_FOUND,
                )
            fenced = FENCE.fullmatch(raw)
            if fenced:
                form = "markdown_fence"
                patch = fenced.group(1) + b"\n"
            elif raw.startswith(DIFF_START) and raw.count(DIFF_START) > 1:
                return self._reject(
                    raw_hash,
                    PatchStage.PATCH_EXTRACTION,
                    V2PatchDiagnosticCode.MULTIPLE_PATCHES_FOUND,
                )
            elif raw.startswith(DIFF_START):
                patch = raw
            elif (
                raw.count(DIFF_START) > 1 or raw.count(b"```diff") > 1 or raw.count(b"```patch") > 1
            ):
                return self._reject(
                    raw_hash,
                    PatchStage.PATCH_EXTRACTION,
                    V2PatchDiagnosticCode.MULTIPLE_PATCHES_FOUND,
                )
            elif DIFF_START in raw or b"```diff" in raw or b"```patch" in raw:
                return self._reject(
                    raw_hash, PatchStage.PATCH_EXTRACTION, V2PatchDiagnosticCode.AMBIGUOUS_RESPONSE
                )
            else:
                return self._reject(
                    raw_hash, PatchStage.PATCH_EXTRACTION, V2PatchDiagnosticCode.NO_PATCH_FOUND
                )
        patch = patch.replace(b"\r\n", b"\n")
        early = self._ceilings(patch)
        if early is not None:
            return self._reject(raw_hash, PatchStage.DIFF_VALIDATION, early)
        if any(
            marker in patch
            for marker in (
                b"\nrename from ",
                b"\nrename to ",
                b"\ncopy from ",
                b"\ncopy to ",
                b"\nGIT binary patch",
                b"\nBinary files ",
                b"\nnew file mode 120000",
                b"\nnew file mode 160000",
            )
        ):
            return self._reject(
                raw_hash,
                PatchStage.DIFF_VALIDATION,
                V2PatchDiagnosticCode.UNSUPPORTED_PATCH_OPERATION,
            )
        inspected = self._inspector.inspect(patch)
        if not inspected.acceptable:
            code = self._map_inspector(patch, inspected.diagnostics)
            return self._reject(raw_hash, PatchStage.DIFF_VALIDATION, code)
        if self._syntactic_noop(patch):
            return self._reject(
                raw_hash,
                PatchStage.DIFF_VALIDATION,
                V2PatchDiagnosticCode.NO_EFFECTIVE_CHANGE,
            )
        if declared and declared != tuple(sorted(inspected.changed_paths)):
            return self._reject(
                raw_hash, PatchStage.POLICY_VALIDATION, V2PatchDiagnosticCode.DECLARED_PATH_MISMATCH
            )
        return ExtractedPatch(
            PATCH_DIAGNOSTIC_SCHEMA,
            form,
            raw_hash,
            hashlib.sha256(patch).hexdigest(),
            patch,
            declared,
            (),
        )

    @staticmethod
    def _structured(data: object) -> RepairResponse:
        if (
            not isinstance(data, dict)
            or set(data) - ALLOWED_FIELDS
            or set(data)
            < {
                "schema_version",
                "task_id",
                "candidate_id",
                "unified_diff",
                "declared_changed_paths",
            }
        ):
            raise ValueError("invalid response fields")
        if data.get("schema_version") != REPAIR_RESPONSE_SCHEMA:
            raise ValueError("unsupported response schema")
        values = cast(dict[str, Any], data)
        paths = values["declared_changed_paths"]
        if not isinstance(paths, list) or not all(isinstance(item, str) for item in paths):
            raise ValueError("invalid declared paths")
        for key in ("task_id", "candidate_id", "unified_diff"):
            if not isinstance(values[key], str):
                raise ValueError("invalid text field")
        rationale = values.get("rationale_summary")
        if rationale is not None and not isinstance(rationale, str):
            raise ValueError("invalid rationale")
        return RepairResponse(
            schema_version=values["schema_version"],
            task_id=values["task_id"],
            candidate_id=values["candidate_id"],
            unified_diff=values["unified_diff"],
            declared_changed_paths=tuple(paths),
            rationale_summary=rationale,
        )

    @staticmethod
    def _ceilings(patch: bytes) -> V2PatchDiagnosticCode | None:
        if len(patch) > MAX_RESPONSE_BYTES:
            return V2PatchDiagnosticCode.PATCH_TOO_LARGE
        lines = patch.splitlines()
        if len(lines) > MAX_PATCH_LINES:
            return V2PatchDiagnosticCode.PATCH_TOO_LARGE
        if sum(line.startswith(DIFF_START) for line in lines) > MAX_PATCH_FILES:
            return V2PatchDiagnosticCode.PATCH_TOO_LARGE
        if sum(line.startswith(b"@@") for line in lines) > MAX_PATCH_HUNKS:
            return V2PatchDiagnosticCode.PATCH_TOO_LARGE
        return None

    @staticmethod
    def _syntactic_noop(patch: bytes) -> bool:
        removed = [
            line[1:]
            for line in patch.splitlines()
            if line.startswith(b"-") and not line.startswith(b"---")
        ]
        added = [
            line[1:]
            for line in patch.splitlines()
            if line.startswith(b"+") and not line.startswith(b"+++")
        ]
        return bool(removed) and removed == added

    @staticmethod
    def _map_inspector(
        patch: bytes, diagnostics: tuple[PatchDiagnostic, ...]
    ) -> V2PatchDiagnosticCode:
        codes = {item.code for item in diagnostics}
        if (
            PatchDiagnosticCode.TOO_LARGE in codes
            or PatchDiagnosticCode.TOO_MANY_OPERATIONS in codes
        ):
            return V2PatchDiagnosticCode.PATCH_TOO_LARGE
        if codes & {
            PatchDiagnosticCode.BINARY,
            PatchDiagnosticCode.RENAME_COPY,
            PatchDiagnosticCode.UNSAFE_MODE,
        }:
            return V2PatchDiagnosticCode.UNSUPPORTED_PATCH_OPERATION
        if codes & {
            PatchDiagnosticCode.UNSAFE_PATH,
            PatchDiagnosticCode.GIT_PATH,
            PatchDiagnosticCode.CONTROL_PATH,
            PatchDiagnosticCode.PATH_TOO_LONG,
            PatchDiagnosticCode.OUTSIDE_ALLOWED_ROOT,
            PatchDiagnosticCode.PROTECTED_PATH,
        }:
            return V2PatchDiagnosticCode.UNSAFE_PATH
        if PatchDiagnosticCode.EMPTY in codes:
            return V2PatchDiagnosticCode.NO_PATCH_FOUND
        hunk = re.search(rb"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", patch, re.MULTILINE)
        if hunk is not None:
            expected_old = int(hunk.group(2) or b"1")
            expected_new = int(hunk.group(4) or b"1")
            body = patch[hunk.end() :].splitlines()[1:]
            old = sum(bool(line) and line[:1] in {b" ", b"-"} for line in body)
            new = sum(bool(line) and line[:1] in {b" ", b"+"} for line in body)
            if old < expected_old or new < expected_new:
                return V2PatchDiagnosticCode.TRUNCATED_DIFF
        return V2PatchDiagnosticCode.MALFORMED_DIFF_HEADER

    @staticmethod
    def _reject(raw_hash: str, stage: PatchStage, code: V2PatchDiagnosticCode) -> ExtractedPatch:
        return ExtractedPatch(
            PATCH_DIAGNOSTIC_SCHEMA,
            "rejected",
            raw_hash,
            None,
            None,
            (),
            (V2PatchDiagnostic.create(stage, code),),
        )
