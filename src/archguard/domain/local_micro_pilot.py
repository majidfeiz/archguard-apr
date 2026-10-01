"""Fail-closed resource limits for the Phase 12.6 local micro-pilot."""

from dataclasses import dataclass

from archguard.domain.repository import check

GIB = 1024**3


@dataclass(frozen=True)
class MicroPilotLimits:
    maximum_additional_disk: int = 18 * GIB
    minimum_free_disk: int = 7 * GIB
    maximum_network_download: int = 5 * GIB
    maximum_unapproved_download: int = 1 * GIB
    maximum_approved_download: int = 3 * GIB
    maximum_benchmark_images: int = 2
    maximum_bugsinpy_tasks: int = 2
    maximum_swe_bench_tasks: int = 1
    maximum_concurrency: int = 1
    maximum_paid_provider_calls: int = 0


DEFAULT_LIMITS = MicroPilotLimits()


@dataclass(frozen=True)
class ResourcePreflight:
    cumulative_download: int
    benchmark_disk_usage: int
    free_disk: int
    operation_download: int
    operation_disk_impact: int
    download_approved: bool = False

    def validate(self, limits: MicroPilotLimits = DEFAULT_LIMITS) -> None:
        values = (
            self.cumulative_download,
            self.benchmark_disk_usage,
            self.free_disk,
            self.operation_download,
            self.operation_disk_impact,
        )
        check(all(value >= 0 for value in values), "negative resource accounting")
        single_limit = (
            limits.maximum_approved_download
            if self.download_approved
            else limits.maximum_unapproved_download
        )
        check(self.operation_download <= single_limit, "single download exceeds approval limit")
        check(
            self.cumulative_download + self.operation_download <= limits.maximum_network_download,
            "cumulative download limit exceeded",
        )
        check(
            self.benchmark_disk_usage + self.operation_disk_impact
            <= limits.maximum_additional_disk,
            "benchmark disk limit exceeded",
        )
        check(
            self.free_disk - self.operation_disk_impact >= limits.minimum_free_disk,
            "minimum free disk would be violated",
        )
