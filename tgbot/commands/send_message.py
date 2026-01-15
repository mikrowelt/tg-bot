"""Send message command."""

from ..utils.config import Config
from ..utils.logger import setup_logger
from ..client import TgBot, SendResult
from .base import run_command

log = setup_logger("tg-bot.cmd.message")


def _parse_target(target: str) -> int | str:
    """Parse target - could be @username, channel ID, or link."""
    if target.startswith("@"):
        return target
    elif target.lstrip("-").isdigit():
        # Handles both positive IDs and negative channel IDs like -1001234567890
        return int(target)
    elif "t.me/" in target:
        parsed = target.split("/")[-1]
        if parsed.startswith("+"):
            return target  # Private link, return full URL
        return parsed
    else:
        return target


async def _send_message(
    target: str,
    text: str,
    profile: str | None,
    comment_to: int | None,
    reply_to: int | None,
) -> SendResult:
    """Internal async implementation. Returns SendResult."""
    config = Config.load(profile)
    parsed_target = _parse_target(target)

    async with TgBot(config) as bot:
        if comment_to:
            result = await bot.send_comment(parsed_target, comment_to, text, reply_to=reply_to)
        else:
            result = await bot.send_message(parsed_target, text, reply_to=reply_to)

    if result.ok:
        log.info(f"Message sent (id={result.message_id})")
    else:
        log.warning(f"Send failed: {result.error} (retryable={result.retryable})")

    return result


def send_message(
    target: str,
    text: str,
    profile: str | None = None,
    comment_to: int | None = None,
    reply_to: int | None = None,
) -> SendResult | None:
    """
    Send a message to a group, channel, or user.

    Args:
        target: Target chat (@username, channel ID, or link)
        text: Message text to send
        profile: Profile name (defaults to PROFILE_NAME env var or "profile")
        comment_to: Post ID to comment on (for channel comments)
        reply_to: Message ID to reply to

    Returns:
        SendResult with ok, message_id, error, retryable, wait_seconds
    """
    return run_command(_send_message)(
        target=target,
        text=text,
        profile=profile,
        comment_to=comment_to,
        reply_to=reply_to,
    )
