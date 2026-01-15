"""Profile health check command."""

from ..utils.config import Config
from ..utils.logger import setup_logger
from ..client import TgBot
from .base import run_command

log = setup_logger("tg-bot.cmd.profile_health")


async def _profile_health_check(
    profile: str | None,
    expected_first_name: str | None,
    expected_last_name: str | None,
    expected_username: str | None,
    expected_about: str | None,
) -> dict:
    """Internal async implementation."""
    config = Config.load(profile)

    async with TgBot(config) as bot:
        return await bot.profile_health_check(
            expected_first_name=expected_first_name,
            expected_last_name=expected_last_name,
            expected_username=expected_username,
            expected_about=expected_about,
        )


def profile_health_check(
    profile: str | None = None,
    expected_first_name: str | None = None,
    expected_last_name: str | None = None,
    expected_username: str | None = None,
    expected_about: str | None = None,
) -> dict | None:
    """
    Run comprehensive profile health check.

    Verifies:
    - Account is not frozen/blocked/restricted/deleted
    - Profile data matches expected values (if provided)

    Args:
        profile: Profile name (defaults to PROFILE_NAME env var or "profile")
        expected_first_name: Expected first name to verify against DB
        expected_last_name: Expected last name to verify against DB
        expected_username: Expected username to verify against DB
        expected_about: Expected bio/about to verify against DB

    Returns:
        Health check result dict with account_status, profile, sync_status, errors
    """
    return run_command(_profile_health_check)(
        profile=profile,
        expected_first_name=expected_first_name,
        expected_last_name=expected_last_name,
        expected_username=expected_username,
        expected_about=expected_about,
    )
