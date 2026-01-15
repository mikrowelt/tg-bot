"""Join channel command."""

from ..utils.config import Config
from ..utils.logger import setup_logger
from ..client import TgBot, JoinChannelError
from .base import run_command

log = setup_logger("tg-bot.cmd.join")


async def _join_channel(
    channel: str,
    profile: str | None,
    skip_verification: bool,
) -> dict:
    """Internal async implementation."""
    config = Config.load(profile)

    async with TgBot(config) as bot:
        channel_id = await bot.join_channel(
            channel_link=channel,
            verify=not skip_verification,
        )
        log.info(f"Channel ID: {channel_id}")

    log.info("Join channel completed successfully")
    return {"success": True, "channel_id": channel_id}


def join_channel(
    channel: str,
    profile: str | None = None,
    skip_verification: bool = False,
) -> dict | None:
    """
    Join a Telegram channel and pass bot verification.

    Args:
        channel: Channel link (https://t.me/... or @username)
        profile: Profile name (defaults to PROFILE_NAME env var or "profile")
        skip_verification: Skip bot verification after joining
    """
    return run_command(
        _join_channel,
        error_types=(JoinChannelError,),
        print_result=False,
    )(
        channel=channel,
        profile=profile,
        skip_verification=skip_verification,
    )
