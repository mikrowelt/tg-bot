"""
Retry utilities for tg-bot.

This module provides retry logic with exponential backoff for
handling transient failures in async operations.
"""
import asyncio
from functools import wraps
from typing import TypeVar, Callable, Any, Coroutine, Type

from .constants import MAX_RETRIES, RETRY_BACKOFF_BASE, DELAY_RATE_LIMIT_BASE
from .logger import setup_logger

log = setup_logger("tg-bot.retry")

T = TypeVar('T')


class RetryExhaustedError(Exception):
    """Raised when all retry attempts have been exhausted."""

    def __init__(self, message: str, last_error: Exception | None = None):
        super().__init__(message)
        self.last_error = last_error


async def retry_with_backoff(
    coro_func: Callable[..., Coroutine[Any, Any, T]],
    *args,
    max_retries: int = MAX_RETRIES,
    base_delay: float = RETRY_BACKOFF_BASE,
    retryable_exceptions: tuple[Type[Exception], ...] = (Exception,),
    operation_name: str = "operation",
    **kwargs,
) -> T:
    """
    Execute a coroutine function with exponential backoff retry.

    Args:
        coro_func: The async function to call
        *args: Arguments to pass to the function
        max_retries: Maximum number of retry attempts
        base_delay: Base delay in seconds (doubles each retry)
        retryable_exceptions: Tuple of exception types to retry on
        operation_name: Name for logging
        **kwargs: Keyword arguments to pass to the function

    Returns:
        The result of the coroutine

    Raises:
        RetryExhaustedError: If all retries are exhausted
    """
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return await coro_func(*args, **kwargs)
        except retryable_exceptions as e:
            last_error = e

            if attempt == max_retries:
                log.error(f"{operation_name} failed after {max_retries + 1} attempts: {e}")
                raise RetryExhaustedError(
                    f"{operation_name} failed after {max_retries + 1} attempts",
                    last_error=e,
                )

            delay = base_delay * (2 ** attempt)
            log.warning(
                f"{operation_name} failed (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                f"Retrying in {delay}s..."
            )
            await asyncio.sleep(delay)

    # Should never reach here, but just in case
    raise RetryExhaustedError(f"{operation_name} failed", last_error=last_error)


def retry_decorator(
    max_retries: int = MAX_RETRIES,
    base_delay: float = RETRY_BACKOFF_BASE,
    retryable_exceptions: tuple[Type[Exception], ...] = (Exception,),
    operation_name: str | None = None,
):
    """
    Decorator to add retry logic with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Base delay in seconds (doubles each retry)
        retryable_exceptions: Tuple of exception types to retry on
        operation_name: Name for logging (defaults to function name)

    Usage:
        @retry_decorator(max_retries=3, retryable_exceptions=(ConnectionError,))
        async def fetch_data():
            ...
    """
    def decorator(func: Callable[..., Coroutine[Any, Any, T]]) -> Callable[..., Coroutine[Any, Any, T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            name = operation_name or func.__name__
            return await retry_with_backoff(
                func,
                *args,
                max_retries=max_retries,
                base_delay=base_delay,
                retryable_exceptions=retryable_exceptions,
                operation_name=name,
                **kwargs,
            )
        return wrapper
    return decorator


class RetryContext:
    """
    Context for manual retry control within a function.

    Usage:
        async def my_operation():
            retry = RetryContext(max_retries=3, operation_name="my_op")

            while retry.should_retry():
                try:
                    result = await do_something()
                    return result
                except SomeError as e:
                    await retry.handle_error(e)

            retry.raise_exhausted()
    """

    def __init__(
        self,
        max_retries: int = MAX_RETRIES,
        base_delay: float = RETRY_BACKOFF_BASE,
        operation_name: str = "operation",
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.operation_name = operation_name
        self.attempt = 0
        self.last_error: Exception | None = None

    def should_retry(self) -> bool:
        """Check if another retry attempt should be made."""
        return self.attempt <= self.max_retries

    async def handle_error(self, error: Exception) -> None:
        """
        Handle an error and wait before the next retry.

        Args:
            error: The exception that occurred
        """
        self.last_error = error
        self.attempt += 1

        if self.attempt > self.max_retries:
            log.error(
                f"{self.operation_name} failed after {self.max_retries + 1} attempts: {error}"
            )
            return

        delay = self.base_delay * (2 ** (self.attempt - 1))
        log.warning(
            f"{self.operation_name} failed (attempt {self.attempt}/{self.max_retries + 1}): {error}. "
            f"Retrying in {delay}s..."
        )
        await asyncio.sleep(delay)

    def raise_exhausted(self) -> None:
        """Raise RetryExhaustedError if all retries are exhausted."""
        if self.attempt > self.max_retries:
            raise RetryExhaustedError(
                f"{self.operation_name} failed after {self.max_retries + 1} attempts",
                last_error=self.last_error,
            )


async def handle_rate_limit(
    wait_seconds: int,
    operation_name: str = "operation",
    extra_buffer: float = DELAY_RATE_LIMIT_BASE,
) -> None:
    """
    Handle a rate limit by waiting the specified time plus a buffer.

    Args:
        wait_seconds: Seconds to wait (from FloodWaitError.seconds)
        operation_name: Name for logging
        extra_buffer: Extra seconds to add to the wait time
    """
    total_wait = wait_seconds + extra_buffer
    log.warning(f"{operation_name} rate limited. Waiting {total_wait}s...")
    await asyncio.sleep(total_wait)
