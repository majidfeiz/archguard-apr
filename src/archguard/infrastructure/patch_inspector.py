"""Bounded inspection of a narrow Git-compatible textual unified-diff subset."""

import hashlib
import re
from pathlib import PurePosixPath, PureWindowsPath

from archguard.domain.patch_validation import (
    CANDIDATE_PATCH_SCHEMA_VERSION,
    MAX_PATCH_BYTES,
    MAX_PATCH_OPERATIONS,
    MAX_PATCH_PATH_BYTES,
    PATCH_MESSAGES,
    CandidatePatch,
    PatchDiagnostic,
    PatchDiagnosticCode,
    PatchOperation,
    PatchOperationKind,
)

DIFF = re.compile(rb"^diff --git a/(.+) b/(.+)$")
HUNK = re.compile(rb"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: .*)?$")


class UnifiedDiffInspector:
    def inspect(
        self, raw: bytes, allowed_roots: tuple[str, ...] = (), protected_paths: tuple[str, ...] = ()
    ) -> CandidatePatch:
        fingerprint = hashlib.sha256(raw).hexdigest()
        diagnostics: set[PatchDiagnosticCode] = set()
        operations: list[PatchOperation] = []
        if not raw:
            diagnostics.add(PatchDiagnosticCode.EMPTY)
        if len(raw) > MAX_PATCH_BYTES:
            diagnostics.add(PatchDiagnosticCode.TOO_LARGE)
        if b"\0" in raw:
            diagnostics.add(PatchDiagnosticCode.NUL)
        if b"GIT binary patch" in raw or b"Binary files " in raw:
            diagnostics.add(PatchDiagnosticCode.BINARY)
        if any(
            token in raw for token in (b"rename from ", b"rename to ", b"copy from ", b"copy to ")
        ):
            diagnostics.add(PatchDiagnosticCode.RENAME_COPY)
        if any(
            token in raw
            for token in (
                b"new file mode 120000",
                b"deleted file mode 120000",
                b"old mode 120000",
                b"new mode 160000",
                b"old mode 160000",
            )
        ):
            diagnostics.add(PatchDiagnosticCode.UNSAFE_MODE)
        if len(raw) <= MAX_PATCH_BYTES and b"\0" not in raw:
            self._parse(raw, operations, diagnostics, allowed_roots, protected_paths)
        if len(operations) > MAX_PATCH_OPERATIONS:
            diagnostics.add(PatchDiagnosticCode.TOO_MANY_OPERATIONS)
            operations = []
        paths = [operation.path for operation in operations]
        if len(paths) != len(set(paths)):
            diagnostics.add(PatchDiagnosticCode.DUPLICATE_PATH)
            operations = []
        normalized = tuple(
            PatchDiagnostic(code, PATCH_MESSAGES[code]) for code in sorted(diagnostics)
        )
        return CandidatePatch(
            CANDIDATE_PATCH_SCHEMA_VERSION,
            fingerprint,
            len(raw),
            tuple(sorted(operations)),
            PatchDiagnosticCode.BINARY in diagnostics,
            normalized,
            bool(operations) and not normalized,
        )

    def _parse(
        self,
        raw: bytes,
        operations: list[PatchOperation],
        diagnostics: set[PatchDiagnosticCode],
        allowed_roots: tuple[str, ...],
        protected_paths: tuple[str, ...],
    ) -> None:
        lines = raw.splitlines()
        indexes = [i for i, line in enumerate(lines) if line.startswith(b"diff --git ")]
        if not indexes or indexes[0] != 0:
            diagnostics.add(PatchDiagnosticCode.MALFORMED)
            return
        indexes.append(len(lines))
        for start, end in zip(indexes, indexes[1:], strict=False):
            section = lines[start:end]
            match = DIFF.fullmatch(section[0])
            if match is None or len(section) < 4:
                diagnostics.add(PatchDiagnosticCode.MALFORMED)
                continue
            try:
                left, right = (value.decode("utf-8") for value in match.groups())
            except UnicodeDecodeError:
                diagnostics.add(PatchDiagnosticCode.UNSAFE_PATH)
                continue
            old_headers = [line[4:] for line in section if line.startswith(b"--- ")]
            new_headers = [line[4:] for line in section if line.startswith(b"+++ ")]
            if len(old_headers) != 1 or len(new_headers) != 1 or not self._valid_hunks(section):
                diagnostics.add(PatchDiagnosticCode.MALFORMED)
                continue
            old, new = old_headers[0], new_headers[0]
            if old == b"/dev/null":
                kind, target, expected_new = PatchOperationKind.ADD, right, ("b/" + right).encode()
                valid = new == expected_new
            elif new == b"/dev/null":
                kind, target = PatchOperationKind.DELETE, left
                valid = old == ("a/" + left).encode()
            else:
                kind, target = PatchOperationKind.MODIFY, right
                valid = (
                    left == right
                    and old == ("a/" + left).encode()
                    and new == ("b/" + right).encode()
                )
            if not valid:
                diagnostics.add(PatchDiagnosticCode.MALFORMED)
                continue
            code = self._path_code(target, allowed_roots, protected_paths)
            if code is not None:
                diagnostics.add(code)
                continue
            operations.append(PatchOperation(target, kind))

    @staticmethod
    def _valid_hunks(section: list[bytes]) -> bool:
        starts = [i for i, line in enumerate(section) if line.startswith(b"@@")]
        if not starts:
            return False
        starts.append(len(section))
        for start, end in zip(starts, starts[1:], strict=False):
            match = HUNK.fullmatch(section[start])
            if match is None:
                return False
            expected_old = int(match.group(2) or b"1")
            expected_new = int(match.group(4) or b"1")
            old = new = 0
            for line in section[start + 1 : end]:
                if line.startswith(b"\\ No newline at end of file"):
                    continue
                if not line or line[:1] not in {b" ", b"+", b"-"}:
                    return False
                old += line[:1] in {b" ", b"-"}
                new += line[:1] in {b" ", b"+"}
            if old != expected_old or new != expected_new:
                return False
        return True

    @staticmethod
    def _path_code(
        path: str, allowed_roots: tuple[str, ...], protected_paths: tuple[str, ...]
    ) -> PatchDiagnosticCode | None:
        posix, windows = PurePosixPath(path), PureWindowsPath(path)
        if len(path.encode("utf-8")) > MAX_PATCH_PATH_BYTES:
            return PatchDiagnosticCode.PATH_TOO_LONG
        if any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in path):
            return PatchDiagnosticCode.CONTROL_PATH
        if (
            posix.is_absolute()
            or windows.anchor
            or ".." in posix.parts
            or ".." in windows.parts
            or "\\" in path
            or posix.as_posix() != path
        ):
            return PatchDiagnosticCode.UNSAFE_PATH
        if posix.parts and posix.parts[0].casefold() == ".git":
            return PatchDiagnosticCode.GIT_PATH
        if allowed_roots and not any(
            path == root or path.startswith(root.rstrip("/") + "/") for root in allowed_roots
        ):
            return PatchDiagnosticCode.OUTSIDE_ALLOWED_ROOT
        if any(path == item or path.startswith(item.rstrip("/") + "/") for item in protected_paths):
            return PatchDiagnosticCode.PROTECTED_PATH
        return None
