from dataclasses import replace

import pytest

from archguard.domain.local_micro_pilot import GIB, MicroPilotLimits, ResourcePreflight


def safe_preflight() -> ResourcePreflight:
    return ResourcePreflight(70_000_000, 12_000_000, 51 * GIB, 100_000_000, 500_000_000)


def test_strict_micro_pilot_limits_are_frozen() -> None:
    limits = MicroPilotLimits()
    assert limits.maximum_additional_disk == 18 * GIB
    assert limits.minimum_free_disk == 7 * GIB
    assert limits.maximum_network_download == 5 * GIB
    assert limits.maximum_unapproved_download == GIB
    assert limits.maximum_approved_download == 3 * GIB
    assert (
        limits.maximum_benchmark_images,
        limits.maximum_bugsinpy_tasks,
        limits.maximum_swe_bench_tasks,
        limits.maximum_concurrency,
        limits.maximum_paid_provider_calls,
    ) == (2, 2, 1, 1, 0)


def test_safe_preflight_passes_and_every_resource_boundary_fails_closed() -> None:
    value = safe_preflight()
    value.validate()
    invalid = (
        replace(value, operation_download=GIB + 1),
        replace(value, cumulative_download=5 * GIB),
        replace(value, benchmark_disk_usage=18 * GIB),
        replace(value, free_disk=7 * GIB),
        replace(value, cumulative_download=-1),
    )
    for candidate in invalid:
        with pytest.raises(ValueError):
            candidate.validate()


def test_explicit_approval_changes_only_the_single_download_ceiling() -> None:
    value = replace(safe_preflight(), operation_download=2 * GIB, download_approved=True)
    value.validate()
    with pytest.raises(ValueError, match="single download"):
        replace(value, operation_download=3 * GIB + 1).validate()
