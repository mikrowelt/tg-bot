import asyncio
import sys

from ..utils.config import Config, ConfigError
from ..utils.logger import setup_logger
from ..client import TgBot, SendMessageError

log = setup_logger("tg-bot.cmd.message")


async def _send_message(
    target: str,
    text: str,
    profile: str | None,
    comment_to: int | None,
    reply_to: int | None,
) -> int:
    """Internal async implementation. Returns the message ID."""
    config = Config.load(profile)

    # Parse target - could be @username, channel ID, or link
    parsed_target: int | str
    if target.startswith("@"):
        parsed_target = target
    elif target.startswith("-") or target.isdigit():
        parsed_target = int(target)
    elif "t.me/" in target:
        parsed_target = target.split("/")[-1]
        if parsed_target.startswith("+"):
            parsed_target = target
    else:
        parsed_target = target

    async with TgBot(config) as bot:
        if comment_to:
            return await bot.send_comment(parsed_target, comment_to, text)
        else:
            return await bot.send_message(parsed_target, text, reply_to=reply_to)


def send_message(
    target: str,
    text: str,
    profile: str | None = None,
    comment_to: int | None = None,
    reply_to: int | None = None,
) -> int | None:
    """
    Send a message to a group, channel, or user.

    Args:
        target: Target chat (@username, channel ID, or link)
        text: Message text to send
        profile: Profile name (defaults to PROFILE_NAME env var or "profile")
        comment_to: Post ID to comment on (for channel comments)
        reply_to: Message ID to reply to

    Returns:
        The message ID of the sent message, or None on error.
    """
    try:
        message_id = asyncio.run(_send_message(
            target=target,
            text=text,
            profile=profile,
            comment_to=comment_to,
            reply_to=reply_to,
        ))
        log.info("Send message completed successfully")
        print(message_id)
        return message_id
    except ConfigError as e:
        log.error(f"Configuration error: {e}")
        sys.exit(1)
    except SendMessageError as e:
        log.error(f"Send message failed: {e}")
        sys.exit(1)
    except Exception as e:
        log.error(f"Unexpected error: {e}")
        sys.exit(1)
