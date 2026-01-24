"""
Async timeout utilities for tg-bot.

This module provides timeout wrappers for async operations to prevent
indefinite hangs on network operations.
"""
import asyncio
from functools import wraps
from typing import TypeVar, Callable, Any, Coroutine

from .constants import TIMEOUT_OPERATION, TIMEOUT_VERIFICATION
from .logger import setup_logger

log = setup_logger("tg-bot.timeout")

T = TypeVar('T')


class TimeoutError(Exception):
    """Raised when an async operation times out."""
    pass


async def with_timeout(
    coro: Coroutine[Any, Any, T],
    timeout: float = TIMEOUT_OPERATION,
    operation_name: str = "operation",
) -> T:
    """
    Execute a coroutine with a timeout.

    Args:
        coro: The coroutine to execute
        timeout: Timeout in seconds (default: TIMEOUT_OPERATION)
        operation_name: Name for logging purposes

    Returns:
        The result of the coroutine

    Raises:
        TimeoutError: If the operation times out
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        log.error(f"{operation_name} timed out after {timeout}s")
        raise TimeoutError(f"{operation_name} timed out after {timeout} seconds")


def timeout_decorator(
    timeout: float = TIMEOUT_OPERATION,
    operation_name: str | None = None,
):
    """
    Decorator to add timeout to an async function.

    Args:
        timeout: Timeout in seconds
        operation_name: Name for logging (defaults to function name)

    Usage:
        @timeout_decorator(timeout=30)
        async def my_long_operation():
            ...
    """
    def decorator(func: Callable[..., Coroutine[Any, Any, T]]) -> Callable[..., Coroutine[Any, Any, T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            name = operation_name or func.__name__
            try:
                return await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                log.error(f"{name} timed out after {timeout}s")
                raise TimeoutError(f"{name} timed out after {timeout} seconds")
        return wrapper
    return decorator


class TimeoutContext:
    """
    Async context manager for operations that need timeout protection.

    Usage:
        async with TimeoutContext(30, "fetch_messages"):
            async for message in client.iter_messages(entity, limit=100):
                process(message)
    """

    def __init__(self, timeout: float, operation_name: str = "operation"):
        self.timeout = timeout
        self.operation_name = operation_name
        self._task: asyncio.Task | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is asyncio.TimeoutError:
            log.error(f"{self.operation_name} timed out after {self.timeout}s")
            raise TimeoutError(f"{self.operation_name} timed out after {self.timeout} seconds")
        return False


async def iter_with_timeout(
    async_iterator,
    timeout: float = TIMEOUT_OPERATION,
    operation_name: str = "iteration",
):
    """
    Wrap an async iterator with a total timeout.

    Args:
        async_iterator: The async iterator to wrap
        timeout: Total timeout for all iterations
        operation_name: Name for logging

    Yields:
        Items from the async iterator

    Raises:
        TimeoutError: If the total iteration time exceeds timeout
    """
    deadline = asyncio.get_event_loop().time() + timeout

    async for item in async_iterator:
        if asyncio.get_event_loop().time() > deadline:
            log.error(f"{operation_name} timed out after {timeout}s")
            raise TimeoutError(f"{operation_name} timed out after {timeout} seconds")
        yield item
