import asyncio
import json
import sys

from ..utils.config import Config, ConfigError
from ..utils.logger import setup_logger
from ..client import TgBot

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
    try:
        result = asyncio.run(_health_check(profile=profile))
        print(json.dumps(result, indent=2))
        return result
    except ConfigError as e:
        log.error(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        log.error(f"Health check error: {e}")
        sys.exit(1)
