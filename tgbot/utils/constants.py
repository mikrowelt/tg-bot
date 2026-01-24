"""
Centralized constants for tg-bot.

This module contains all magic numbers, timeouts, and wait time ranges
used throughout the codebase.
"""

from typing import Tuple

# Wait time ranges for anti-detection delays (min_seconds, max_seconds)
# Used with random.uniform() to add human-like delays

# Short delays - minimal waits between quick operations
WAIT_TINY: Tuple[float, float] = (0.5, 1.5)  # Button clicks, quick responses
WAIT_SHORT: Tuple[float, float] = (1, 2)  # Between rapid operations
WAIT_NORMAL: Tuple[float, float] = (1, 3)  # Standard operation delays

# Medium delays - typical operation waits
WAIT_MEDIUM: Tuple[float, float] = (2, 4)  # After sending messages
WAIT_MEDIUM_LONG: Tuple[float, float] = (2, 5)  # Verification steps
WAIT_VERIFICATION: Tuple[float, float] = (3, 5)  # Verification attempts
WAIT_HUMAN: Tuple[float, float] = (3, 6)  # Simulating human reading/response
WAIT_PROFILE: Tuple[float, float] = (3, 7)  # Profile operations

# Long delays - extended waits for sensitive operations
WAIT_LONG: Tuple[float, float] = (4, 7)  # After PM verification
WAIT_RATE_LIMIT_EXTRA: Tuple[float, float] = (5, 10)  # After rate limit recovery

# Fixed delays (seconds)
DELAY_POLL: float = 0.1  # Polling loops
DELAY_PAGINATION: float = 0.5  # Between pagination requests
DELAY_RETRY: float = 2  # Between retry attempts
DELAY_VERIFICATION_STATUS: float = 3  # Verification status checks
DELAY_CAPTCHA_POLL: float = 5  # Captcha solution polling
DELAY_CAPTCHA_INITIAL: float = 10  # Initial captcha wait
DELAY_RATE_LIMIT_BASE: float = 5  # Added to FloodWait seconds

# Timeouts (seconds)
TIMEOUT_OPERATION: int = 30  # Default operation timeout
TIMEOUT_VERIFICATION: int = 60  # Verification process timeout
TIMEOUT_CAPTCHA: int = 120  # Captcha solving timeout

# Retry configuration
MAX_RETRIES: int = 3
RETRY_BACKOFF_BASE: int = 30  # Base seconds for exponential backoff

# Telegram-specific constants
CHANNEL_ID_PREFIX: int = -100  # Prefix for supergroup/channel IDs
DEFAULT_DIALOG_LIMIT: int = 100  # Default limit for dialog iteration
DEFAULT_MESSAGE_LIMIT: int = 50  # Default limit for message iteration

# Rate limiting
RATE_LIMIT_JITTER: Tuple[float, float] = (1, 5)  # Random jitter for rate limits


def random_wait(wait_range: Tuple[float, float]) -> float:
    """
    Generate a random wait time within the given range.

    Args:
        wait_range: Tuple of (min_seconds, max_seconds)

    Returns:
        Random float between min and max seconds
    """
    import random
    return random.uniform(wait_range[0], wait_range[1])
