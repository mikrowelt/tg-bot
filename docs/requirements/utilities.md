# Utility Modules

## Overview

Shared utilities for timing, retry logic, and timeout handling across tg-bot.

---

## Constants (`tgbot/utils/constants.py`)

Centralized constants for all magic numbers, timeouts, and wait time ranges.

### Wait Time Ranges

Used with `random.uniform()` for human-like delays:

```python
# Short delays
WAIT_TINY: Tuple[float, float] = (0.5, 1.5)      # Button clicks
WAIT_SHORT: Tuple[float, float] = (1, 2)         # Rapid operations
WAIT_NORMAL: Tuple[float, float] = (1, 3)        # Standard delays

# Medium delays
WAIT_MEDIUM: Tuple[float, float] = (2, 4)        # After sending messages
WAIT_MEDIUM_LONG: Tuple[float, float] = (2, 5)   # Verification steps
WAIT_VERIFICATION: Tuple[float, float] = (3, 5)  # Verification attempts
WAIT_HUMAN: Tuple[float, float] = (3, 6)         # Human reading time
WAIT_PROFILE: Tuple[float, float] = (3, 7)       # Profile operations

# Long delays
WAIT_LONG: Tuple[float, float] = (4, 7)          # After PM verification
WAIT_RATE_LIMIT_EXTRA: Tuple[float, float] = (5, 10)  # After rate limit
```

### Fixed Delays (seconds)

```python
DELAY_POLL: float = 0.1             # Polling loops
DELAY_PAGINATION: float = 0.5       # Between pagination requests
DELAY_RETRY: float = 2              # Between retry attempts
DELAY_VERIFICATION_STATUS: float = 3  # Verification status checks
DELAY_CAPTCHA_POLL: float = 5       # Captcha solution polling
DELAY_CAPTCHA_INITIAL: float = 10   # Initial captcha wait
DELAY_RATE_LIMIT_BASE: float = 5    # Added to FloodWait seconds
```

### Timeouts (seconds)

```python
TIMEOUT_OPERATION: int = 30      # Default operation timeout
TIMEOUT_VERIFICATION: int = 60   # Verification process timeout
TIMEOUT_CAPTCHA: int = 120       # Captcha solving timeout
```

### Retry Configuration

```python
MAX_RETRIES: int = 3             # Maximum retry attempts
RETRY_BACKOFF_BASE: int = 30     # Base seconds for exponential backoff
```

### Telegram Constants

```python
CHANNEL_ID_PREFIX: int = -100         # Supergroup/channel ID prefix
DEFAULT_DIALOG_LIMIT: int = 100       # Default dialog iteration limit
DEFAULT_MESSAGE_LIMIT: int = 50       # Default message iteration limit
RATE_LIMIT_JITTER: Tuple[float, float] = (1, 5)  # Random jitter
```

### Helper Function

```python
def random_wait(wait_range: Tuple[float, float]) -> float:
    """
    Generate a random wait time within the given range.

    Args:
        wait_range: Tuple of (min_seconds, max_seconds)

    Returns:
        Random float between min and max seconds
    """
```

### Usage

```python
import asyncio
from tgbot.utils.constants import WAIT_NORMAL, WAIT_VERIFICATION, random_wait

# Random delay
await asyncio.sleep(random_wait(WAIT_NORMAL))

# Use in operations
await asyncio.sleep(random_wait(WAIT_VERIFICATION))
```

---

## Retry Utilities (`tgbot/utils/retry.py`)

Retry logic with exponential backoff for transient failures.

### Classes

```python
class RetryExhaustedError(Exception):
    """Raised when all retry attempts have been exhausted."""

    def __init__(self, message: str, last_error: Exception | None = None):
        self.last_error = last_error
```

```python
class RetryContext:
    """
    Context for manual retry control within a function.

    Attributes:
        max_retries: int - Maximum retry attempts
        base_delay: float - Base delay in seconds
        operation_name: str - Name for logging
        attempt: int - Current attempt number
        last_error: Exception | None - Last error encountered
    """

    def __init__(
        self,
        max_retries: int = MAX_RETRIES,
        base_delay: float = RETRY_BACKOFF_BASE,
        operation_name: str = "operation",
    ): ...

    def should_retry(self) -> bool:
        """Check if another retry attempt should be made."""

    async def handle_error(self, error: Exception) -> None:
        """Handle an error and wait before the next retry."""

    def raise_exhausted(self) -> None:
        """Raise RetryExhaustedError if all retries are exhausted."""
```

### Functions

```python
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
        max_retries: Maximum number of retry attempts
        base_delay: Base delay in seconds (doubles each retry)
        retryable_exceptions: Tuple of exception types to retry on
        operation_name: Name for logging

    Returns:
        The result of the coroutine

    Raises:
        RetryExhaustedError: If all retries are exhausted
    """
```

```python
def retry_decorator(
    max_retries: int = MAX_RETRIES,
    base_delay: float = RETRY_BACKOFF_BASE,
    retryable_exceptions: tuple[Type[Exception], ...] = (Exception,),
    operation_name: str | None = None,
):
    """
    Decorator to add retry logic with exponential backoff.

    Usage:
        @retry_decorator(max_retries=3, retryable_exceptions=(ConnectionError,))
        async def fetch_data():
            ...
    """
```

```python
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
```

### Usage Examples

```python
from tgbot.utils.retry import retry_with_backoff, retry_decorator, RetryContext

# Using retry_with_backoff
result = await retry_with_backoff(
    fetch_data,
    url="https://api.example.com",
    max_retries=3,
    retryable_exceptions=(ConnectionError, TimeoutError),
    operation_name="fetch_data",
)

# Using decorator
@retry_decorator(max_retries=3, retryable_exceptions=(ConnectionError,))
async def fetch_data():
    return await client.request()

# Using RetryContext for manual control
async def my_operation():
    retry = RetryContext(max_retries=3, operation_name="my_op")

    while retry.should_retry():
        try:
            result = await do_something()
            return result
        except SomeError as e:
            await retry.handle_error(e)

    retry.raise_exhausted()
```

---

## Timeout Utilities (`tgbot/utils/timeout.py`)

Async timeout wrappers to prevent indefinite hangs.

### Classes

```python
class TimeoutError(Exception):
    """Raised when an async operation times out."""
```

```python
class TimeoutContext:
    """
    Async context manager for operations that need timeout protection.

    Usage:
        async with TimeoutContext(30, "fetch_messages"):
            async for message in client.iter_messages(entity, limit=100):
                process(message)
    """

    def __init__(self, timeout: float, operation_name: str = "operation"): ...
    async def __aenter__(self): ...
    async def __aexit__(self, exc_type, exc_val, exc_tb): ...
```

### Functions

```python
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
```

```python
def timeout_decorator(
    timeout: float = TIMEOUT_OPERATION,
    operation_name: str | None = None,
):
    """
    Decorator to add timeout to an async function.

    Usage:
        @timeout_decorator(timeout=30)
        async def my_long_operation():
            ...
    """
```

```python
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
```

### Usage Examples

```python
from tgbot.utils.timeout import with_timeout, timeout_decorator, iter_with_timeout

# Using with_timeout
result = await with_timeout(
    fetch_data(),
    timeout=30,
    operation_name="fetch_data",
)

# Using decorator
@timeout_decorator(timeout=60)
async def long_running_operation():
    return await process_data()

# Using iter_with_timeout
async for message in iter_with_timeout(
    client.iter_messages(entity, limit=100),
    timeout=30,
    operation_name="fetch_messages",
):
    process(message)
```

---

## ast-grep Search Patterns

```python
# Find constant usage
"WAIT_VERIFICATION"
"TIMEOUT_OPERATION"
"random_wait($$$)"

# Find retry usage
"retry_with_backoff($$$)"
"@retry_decorator($$$)"
"RetryContext($$$)"

# Find timeout usage
"with_timeout($$$)"
"@timeout_decorator($$$)"
"iter_with_timeout($$$)"
```
