"""Health check command."""

from ..utils.config import Config
from ..utils.logger import setup_logger
from ..client import TgBot
from .base import run_command

log = setup_logger("tg-bot.cmd.health")


async def _health_check(profile: str | None) -> dict:
    """Internal async implementation."""
    config = Config.load(profile)

    async with TgBot(config) as bot:
        return await bot.health_check()


def health_check(profile: str | None = None) -> dict | None:
    """
    Check if the Telegram client is healthy and ready to send messages.

    Args:
        profile: Profile name (defaults to PROFILE_NAME env var or "profile")

    Returns:
        Health check result dict, or None on error.
    """
    return run_command(_health_check)(profile=profile)
