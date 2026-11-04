"""Application workflow for provider-neutral V2 response extraction."""

from archguard.application.ports.v2_patch import RepairResponseExtractor
from archguard.domain.v2_patch import ExtractedPatch


class ExtractRepairResponse:
    def __init__(self, extractor: RepairResponseExtractor) -> None:
        self._extractor = extractor

    def execute(self, raw: bytes) -> ExtractedPatch:
        return self._extractor.extract(raw)
