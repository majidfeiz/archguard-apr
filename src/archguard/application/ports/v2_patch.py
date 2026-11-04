"""Ports for V2 repair-response extraction."""

from typing import Protocol

from archguard.domain.v2_patch import ExtractedPatch


class RepairResponseExtractor(Protocol):
    def extract(self, raw: bytes) -> ExtractedPatch: ...
