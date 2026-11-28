"""Bounded retry policy driven only by normalized error categories."""

from collections.abc import Callable
from dataclasses import dataclass

from archguard.domain.providers import (
    ProviderErrorCategory,
    ProviderFailure,
    ProviderResponseState,
    ProviderUsage,
)

RETRYABLE = frozenset(
    {
        ProviderErrorCategory.RATE_LIMITED,
        ProviderErrorCategory.OVERLOADED,
        ProviderErrorCategory.UNAVAILABLE,
        ProviderErrorCategory.NETWORK,
        ProviderErrorCategory.TIMEOUT,
    }
)


@dataclass(frozen=True)
class RetrySchedule:
    maximum_attempts: int
    maximum_delay_seconds: float
    jitter: Callable[[int], float] = lambda _: 0.0

    def delay(self, attempt: int, failure: ProviderFailure) -> float:
        if failure.category not in RETRYABLE or not failure.retryable:
            raise ValueError("failure is not retryable")
        guided = failure.retry_after_seconds
        computed = min(self.maximum_delay_seconds, 2 ** max(0, attempt - 1) + self.jitter(attempt))
        return min(self.maximum_delay_seconds, guided if guided is not None else computed)


class ProviderInvocationError(RuntimeError):
    def __init__(
        self,
        failure: ProviderFailure,
        usage: ProviderUsage | None = None,
        response_state: ProviderResponseState = ProviderResponseState.NOT_RECEIVED,
    ) -> None:
        if usage is not None and not failure.usage_returned:
            raise ValueError("trustworthy usage was not marked returned")
        if usage is None and response_state != ProviderResponseState.NOT_RECEIVED:
            raise ValueError("response state requires trustworthy provider usage")
        super().__init__(failure.public_message)
        self.failure = failure
        self.usage = usage
        self.response_state = response_state


def with_retry[T](
    operation: Callable[[], T], schedule: RetrySchedule, sleep: Callable[[float], None]
) -> T:
    for attempt in range(1, schedule.maximum_attempts + 1):
        try:
            return operation()
        except ProviderInvocationError as error:
            if (
                attempt == schedule.maximum_attempts
                or error.failure.category not in RETRYABLE
                or not error.failure.retryable
            ):
                raise
            sleep(schedule.delay(attempt, error.failure))
    raise AssertionError("unreachable")
