"""Rate limit handling utilities."""

import asyncio
import random

from telethon.errors import FloodWaitError

from .logger import setup_logger

log = setup_logger("tg-bot.rate_limit")


async def handle_flood_wait(
    error: FloodWaitError,
    context: str = "operation",
    add_jitter: bool = True,
) -> None:
    """
    Handle a FloodWaitError by sleeping for the required time.

    Args:
        error: The FloodWaitError to handle
        context: Description of what operation was rate limited (for logging)
        add_jitter: If True, add random jitter (1-5s) to avoid thundering herd
    """
    wait_time = error.seconds
    if add_jitter:
        wait_time += random.uniform(1, 5)

    log.warning(f"Rate limited during {context}, waiting {wait_time:.1f}s")
    await asyncio.sleep(wait_time)


async def retry_on_flood(
    coro_func,
    *args,
    max_retries: int = 3,
    context: str = "operation",
    **kwargs,
):
    """
    Retry an async operation on FloodWaitError.

    Args:
        coro_func: Async function to call
        *args: Arguments for the function
        max_retries: Maximum number of retries (default 3)
        context: Description for logging
        **kwargs: Keyword arguments for the function

    Returns:
        The result of the coroutine

    Raises:
        FloodWaitError: If max retries exceeded
        Any other exception from the coroutine
    """
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            return await coro_func(*args, **kwargs)
        except FloodWaitError as e:
            last_error = e
            if attempt < max_retries:
                await handle_flood_wait(e, context=f"{context} (attempt {attempt + 1})")
            else:
                log.error(f"Max retries exceeded for {context}")
                raise

    raise last_error  # Should never reach here, but for type safety
