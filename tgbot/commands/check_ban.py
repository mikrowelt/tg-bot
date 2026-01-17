"""Check ban status command."""

from ..utils.config import Config
from ..utils.logger import setup_logger
from ..client import TgBot
from .base import run_command

log = setup_logger("tg-bot.cmd.check_ban")


def _parse_target(target: str) -> int | str:
    """Parse target - could be @username, channel ID, or link."""
    if target.startswith("@"):
        return target
    elif target.lstrip("-").isdigit():
        return int(target)
    elif "t.me/" in target:
        parsed = target.split("/")[-1]
        if parsed.startswith("+"):
            return target  # Private link, return full URL
        return parsed
    else:
        return target


async def _check_ban(
    target: str,
    profile: str | None,
    test_message: bool,
) -> dict:
    """
    Internal async implementation.

    Returns dict with:
        - target: The channel/group checked
        - is_member: Whether account is a member
        - is_banned: Whether account is banned (can't write)
        - can_write: Whether account can send messages
        - error: Error message if any
        - details: Additional details
    """
    config = Config.load(profile)
    parsed_target = _parse_target(target)

    result = {
        "target": target,
        "is_member": False,
        "is_banned": False,
        "can_write": False,
        "error": None,
        "details": {},
    }

    async with TgBot(config) as bot:
        # Step 1: Check membership
        membership = await bot.check_channel_membership(parsed_target)
        result["is_member"] = membership["is_member"]
        result["details"]["target_type"] = membership.get("target_type")
        result["details"]["channel_id"] = membership.get("channel_id")

        if not membership["is_member"]:
            result["error"] = membership.get("error", "Not a member of the channel")
            log.info(f"Not a member of {target}")
            return result

        log.info(f"Account is a member of {target} (type: {membership.get('target_type')})")

        # Step 2: If test_message is requested, try to send a test message
        if test_message:
            log.info(f"Testing write access to {target}...")
            # Try sending a message that will be deleted immediately
            # Using a message that looks like a test
            send_result = await bot.send_message(parsed_target, ".")

            if send_result.ok:
                result["can_write"] = True
                result["is_banned"] = False
                result["details"]["test_message_id"] = send_result.message_id
                log.info(f"Write access confirmed (sent message {send_result.message_id})")

                # Try to delete the test message
                try:
                    await bot.client.delete_messages(parsed_target, [send_result.message_id])
                    result["details"]["test_message_deleted"] = True
                    log.info("Test message deleted")
                except Exception as e:
                    result["details"]["test_message_deleted"] = False
                    result["details"]["delete_error"] = str(e)
                    log.warning(f"Could not delete test message: {e}")
            else:
                result["can_write"] = False
                result["error"] = send_result.error
                result["details"]["error_retryable"] = send_result.retryable

                if send_result.error in ("banned", "forbidden", "chat_restricted"):
                    result["is_banned"] = True
                    log.warning(f"Account is BANNED from {target}: {send_result.error}")
                elif send_result.error == "slow_mode":
                    result["can_write"] = True  # Not banned, just rate limited
                    result["is_banned"] = False
                    result["details"]["slow_mode_wait"] = send_result.wait_seconds
                    log.info(f"Slow mode active, wait {send_result.wait_seconds}s")
                else:
                    log.warning(f"Cannot write to {target}: {send_result.error}")
        else:
            # Without test_message, we can only confirm membership
            result["details"]["note"] = "Use --test-message to verify write access"
            log.info("Membership confirmed. Use --test-message to test write access.")

    return result


def check_ban(
    target: str,
    profile: str | None = None,
    test_message: bool = False,
) -> dict | None:
    """
    Check if account is banned from a channel/group.

    Args:
        target: Target chat (@username, channel ID, or link)
        profile: Profile name (defaults to PROFILE_NAME env var or "profile")
        test_message: If True, send a test message to verify write access

    Returns:
        Dict with is_member, is_banned, can_write, error, details
    """
    return run_command(_check_ban)(
        target=target,
        profile=profile,
        test_message=test_message,
    )
