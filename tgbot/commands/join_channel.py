import asyncio
import sys

from ..utils.config import Config, ConfigError
from ..utils.logger import setup_logger
from ..client import TgBot, JoinChannelError

log = setup_logger("tg-bot.cmd.join")


async def _join_channel(
    channel: str,
    profile: str | None,
    skip_verification: bool,
) -> None:
    """Internal async implementation."""
    config = Config.load(profile)

    async with TgBot(config) as bot:
        channel_id = await bot.join_channel(
            channel_link=channel,
            verify=not skip_verification,
        )
        log.info(f"Channel ID: {channel_id}")


def join_channel(
    channel: str,
    profile: str | None = None,
    skip_verification: bool = False,
) -> None:
    """
    Join a Telegram channel and pass bot verification.

    Args:
        channel: Channel link (https://t.me/... or @username)
        profile: Profile name (defaults to PROFILE_NAME env var or "profile")
        skip_verification: Skip bot verification after joining
    """
    try:
        asyncio.run(_join_channel(
            channel=channel,
            profile=profile,
            skip_verification=skip_verification,
        ))
        log.info("Join channel completed successfully")
    except ConfigError as e:
        log.error(f"Configuration error: {e}")
        sys.exit(1)
    except JoinChannelError as e:
        log.error(f"Join channel failed: {e}")
        sys.exit(1)
    except Exception as e:
        log.error(f"Unexpected error: {e}")
        sys.exit(1)
