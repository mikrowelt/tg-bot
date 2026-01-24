"""Tests for tgbot.utils.constants module."""

import pytest
from tgbot.utils.constants import (
    WAIT_TINY,
    WAIT_SHORT,
    WAIT_NORMAL,
    WAIT_MEDIUM,
    WAIT_MEDIUM_LONG,
    WAIT_VERIFICATION,
    WAIT_HUMAN,
    WAIT_PROFILE,
    WAIT_LONG,
    WAIT_RATE_LIMIT_EXTRA,
    DELAY_POLL,
    DELAY_PAGINATION,
    DELAY_RETRY,
    DELAY_VERIFICATION_STATUS,
    DELAY_CAPTCHA_POLL,
    DELAY_CAPTCHA_INITIAL,
    DELAY_RATE_LIMIT_BASE,
    TIMEOUT_OPERATION,
    TIMEOUT_VERIFICATION,
    TIMEOUT_CAPTCHA,
    MAX_RETRIES,
    RETRY_BACKOFF_BASE,
    CHANNEL_ID_PREFIX,
    DEFAULT_DIALOG_LIMIT,
    DEFAULT_MESSAGE_LIMIT,
    RATE_LIMIT_JITTER,
    random_wait,
)


class TestWaitTimeRanges:
    """Test wait time range constants."""

    def test_wait_tiny_is_tuple(self):
        """Verify WAIT_TINY is a valid range tuple."""
        assert isinstance(WAIT_TINY, tuple)
        assert len(WAIT_TINY) == 2
        assert WAIT_TINY[0] < WAIT_TINY[1]

    def test_wait_short_is_tuple(self):
        """Verify WAIT_SHORT is a valid range tuple."""
        assert isinstance(WAIT_SHORT, tuple)
        assert len(WAIT_SHORT) == 2
        assert WAIT_SHORT[0] < WAIT_SHORT[1]

    def test_wait_normal_is_tuple(self):
        """Verify WAIT_NORMAL is a valid range tuple."""
        assert isinstance(WAIT_NORMAL, tuple)
        assert len(WAIT_NORMAL) == 2
        assert WAIT_NORMAL[0] < WAIT_NORMAL[1]

    def test_wait_medium_is_tuple(self):
        """Verify WAIT_MEDIUM is a valid range tuple."""
        assert isinstance(WAIT_MEDIUM, tuple)
        assert len(WAIT_MEDIUM) == 2
        assert WAIT_MEDIUM[0] < WAIT_MEDIUM[1]

    def test_wait_medium_long_is_tuple(self):
        """Verify WAIT_MEDIUM_LONG is a valid range tuple."""
        assert isinstance(WAIT_MEDIUM_LONG, tuple)
        assert len(WAIT_MEDIUM_LONG) == 2
        assert WAIT_MEDIUM_LONG[0] < WAIT_MEDIUM_LONG[1]

    def test_wait_verification_is_tuple(self):
        """Verify WAIT_VERIFICATION is a valid range tuple."""
        assert isinstance(WAIT_VERIFICATION, tuple)
        assert len(WAIT_VERIFICATION) == 2
        assert WAIT_VERIFICATION[0] < WAIT_VERIFICATION[1]

    def test_wait_human_is_tuple(self):
        """Verify WAIT_HUMAN is a valid range tuple."""
        assert isinstance(WAIT_HUMAN, tuple)
        assert len(WAIT_HUMAN) == 2
        assert WAIT_HUMAN[0] < WAIT_HUMAN[1]

    def test_wait_profile_is_tuple(self):
        """Verify WAIT_PROFILE is a valid range tuple."""
        assert isinstance(WAIT_PROFILE, tuple)
        assert len(WAIT_PROFILE) == 2
        assert WAIT_PROFILE[0] < WAIT_PROFILE[1]

    def test_wait_long_is_tuple(self):
        """Verify WAIT_LONG is a valid range tuple."""
        assert isinstance(WAIT_LONG, tuple)
        assert len(WAIT_LONG) == 2
        assert WAIT_LONG[0] < WAIT_LONG[1]

    def test_wait_rate_limit_extra_is_tuple(self):
        """Verify WAIT_RATE_LIMIT_EXTRA is a valid range tuple."""
        assert isinstance(WAIT_RATE_LIMIT_EXTRA, tuple)
        assert len(WAIT_RATE_LIMIT_EXTRA) == 2
        assert WAIT_RATE_LIMIT_EXTRA[0] < WAIT_RATE_LIMIT_EXTRA[1]

    def test_wait_ranges_are_increasing(self):
        """Verify wait ranges are ordered from short to long."""
        ranges = [
            ("WAIT_TINY", WAIT_TINY),
            ("WAIT_SHORT", WAIT_SHORT),
            ("WAIT_NORMAL", WAIT_NORMAL),
            ("WAIT_MEDIUM", WAIT_MEDIUM),
            ("WAIT_LONG", WAIT_LONG),
        ]
        # Each range's min should be less than or equal to next range's min
        for i in range(len(ranges) - 1):
            name, current = ranges[i]
            next_name, next_range = ranges[i + 1]
            assert current[0] <= next_range[0], f"{name} min > {next_name} min"


class TestFixedDelays:
    """Test fixed delay constants."""

    def test_delay_poll_positive(self):
        """Verify DELAY_POLL is positive."""
        assert DELAY_POLL > 0
        assert DELAY_POLL < 1  # Should be sub-second

    def test_delay_pagination_positive(self):
        """Verify DELAY_PAGINATION is positive."""
        assert DELAY_PAGINATION > 0
        assert DELAY_PAGINATION <= 1  # Should be small

    def test_delay_retry_positive(self):
        """Verify DELAY_RETRY is positive."""
        assert DELAY_RETRY > 0

    def test_delay_verification_status_positive(self):
        """Verify DELAY_VERIFICATION_STATUS is positive."""
        assert DELAY_VERIFICATION_STATUS > 0

    def test_delay_captcha_poll_positive(self):
        """Verify DELAY_CAPTCHA_POLL is positive."""
        assert DELAY_CAPTCHA_POLL > 0

    def test_delay_captcha_initial_positive(self):
        """Verify DELAY_CAPTCHA_INITIAL is positive."""
        assert DELAY_CAPTCHA_INITIAL > 0
        assert DELAY_CAPTCHA_INITIAL > DELAY_CAPTCHA_POLL

    def test_delay_rate_limit_base_positive(self):
        """Verify DELAY_RATE_LIMIT_BASE is positive."""
        assert DELAY_RATE_LIMIT_BASE > 0


class TestTimeouts:
    """Test timeout constants."""

    def test_timeout_operation_positive(self):
        """Verify TIMEOUT_OPERATION is positive."""
        assert TIMEOUT_OPERATION > 0

    def test_timeout_verification_positive(self):
        """Verify TIMEOUT_VERIFICATION is positive."""
        assert TIMEOUT_VERIFICATION > 0
        assert TIMEOUT_VERIFICATION >= TIMEOUT_OPERATION

    def test_timeout_captcha_positive(self):
        """Verify TIMEOUT_CAPTCHA is positive."""
        assert TIMEOUT_CAPTCHA > 0
        assert TIMEOUT_CAPTCHA >= TIMEOUT_VERIFICATION


class TestRetryConfig:
    """Test retry configuration constants."""

    def test_max_retries_positive(self):
        """Verify MAX_RETRIES is positive."""
        assert MAX_RETRIES > 0
        assert MAX_RETRIES <= 10  # Sanity check

    def test_retry_backoff_base_positive(self):
        """Verify RETRY_BACKOFF_BASE is positive."""
        assert RETRY_BACKOFF_BASE > 0


class TestTelegramConstants:
    """Test Telegram-specific constants."""

    def test_channel_id_prefix_negative(self):
        """Verify CHANNEL_ID_PREFIX is correct for Telegram."""
        assert CHANNEL_ID_PREFIX == -100

    def test_default_dialog_limit_positive(self):
        """Verify DEFAULT_DIALOG_LIMIT is reasonable."""
        assert DEFAULT_DIALOG_LIMIT > 0
        assert DEFAULT_DIALOG_LIMIT <= 500

    def test_default_message_limit_positive(self):
        """Verify DEFAULT_MESSAGE_LIMIT is reasonable."""
        assert DEFAULT_MESSAGE_LIMIT > 0
        assert DEFAULT_MESSAGE_LIMIT <= 200


class TestRateLimitJitter:
    """Test rate limit jitter constant."""

    def test_rate_limit_jitter_is_tuple(self):
        """Verify RATE_LIMIT_JITTER is a valid range tuple."""
        assert isinstance(RATE_LIMIT_JITTER, tuple)
        assert len(RATE_LIMIT_JITTER) == 2
        assert RATE_LIMIT_JITTER[0] < RATE_LIMIT_JITTER[1]


class TestRandomWait:
    """Test random_wait helper function."""

    def test_random_wait_returns_float(self):
        """Verify random_wait returns a float."""
        result = random_wait(WAIT_NORMAL)
        assert isinstance(result, float)

    def test_random_wait_within_range(self):
        """Verify random_wait returns value within range."""
        for _ in range(100):
            result = random_wait(WAIT_NORMAL)
            assert WAIT_NORMAL[0] <= result <= WAIT_NORMAL[1]

    def test_random_wait_with_custom_range(self):
        """Verify random_wait works with custom range."""
        custom_range = (5.0, 10.0)
        for _ in range(100):
            result = random_wait(custom_range)
            assert custom_range[0] <= result <= custom_range[1]

    def test_random_wait_distribution(self):
        """Verify random_wait produces varied results."""
        results = [random_wait(WAIT_NORMAL) for _ in range(100)]
        # Should have many unique values (randomness)
        unique_values = len(set(results))
        assert unique_values > 50  # At least 50 unique values out of 100
