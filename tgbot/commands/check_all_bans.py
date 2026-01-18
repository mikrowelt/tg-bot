"""Check ban status across all channels command."""

from ..utils.config import Config
from ..utils.logger import setup_logger
from ..client import TgBot
from .base import run_command

log = setup_logger("tg-bot.cmd.check_all_bans")


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


async def _check_all_bans(
    channels: list[str],
    profile: str | None,
    test_message: bool,
) -> dict:
    """
    Internal async implementation.

    Checks ban status for multiple channels and returns summary.

    Returns dict with:
        - total: Total channels checked
        - member_count: Channels where account is a member
        - banned_count: Channels where account is banned
        - not_member_count: Channels where account is not a member
        - health_score: Percentage (0-100) of channels without bans
        - results: List of per-channel results
    """
    config = Config.load(profile)

    results = []
    member_count = 0
    banned_count = 0
    not_member_count = 0

    async with TgBot(config) as bot:
        for channel in channels:
            parsed_target = _parse_target(channel)

            result = {
                "channel": channel,
                "is_member": False,
                "is_banned": False,
                "can_write": False,
                "error": None,
            }

            try:
                # Step 1: Check membership
                membership = await bot.check_channel_membership(parsed_target)
                result["is_member"] = membership["is_member"]
                result["channel_id"] = membership.get("channel_id")

                if not membership["is_member"]:
                    result["error"] = membership.get("error", "Not a member")
                    not_member_count += 1
                    log.info(f"Not a member of {channel}")
                else:
                    member_count += 1

                    # Step 2: If test_message is requested, try to send a test message
                    if test_message:
                        log.info(f"Testing write access to {channel}...")
                        send_result = await bot.send_message(parsed_target, ".")

                        if send_result.ok:
                            result["can_write"] = True
                            result["is_banned"] = False

                            # Delete the test message
                            try:
                                await bot.client.delete_messages(
                                    parsed_target, [send_result.message_id]
                                )
                            except Exception as e:
                                log.warning(f"Could not delete test message: {e}")
                        else:
                            result["can_write"] = False
                            result["error"] = send_result.error

                            if send_result.error in ("banned", "forbidden", "chat_restricted"):
                                result["is_banned"] = True
                                banned_count += 1
                                log.warning(f"BANNED from {channel}: {send_result.error}")
                            elif send_result.error == "slow_mode":
                                result["can_write"] = True
                                result["is_banned"] = False
                            else:
                                log.warning(f"Cannot write to {channel}: {send_result.error}")

            except Exception as e:
                result["error"] = str(e)
                log.error(f"Error checking {channel}: {e}")

            results.append(result)

    # Calculate health score
    total = len(channels)
    # Health is based on members - bans
    if member_count > 0:
        health_score = 100.0 * (1 - banned_count / member_count)
    elif total > 0:
        health_score = 0.0  # No memberships at all
    else:
        health_score = 100.0  # No channels to check

    return {
        "total": total,
        "member_count": member_count,
        "banned_count": banned_count,
        "not_member_count": not_member_count,
        "health_score": round(health_score, 1),
        "results": results,
    }


def check_all_bans(
    channels: list[str],
    profile: str | None = None,
    test_message: bool = True,
) -> dict | None:
    """
    Check ban status across multiple channels.

    Args:
        channels: List of channel targets (@username, channel ID, or link)
        profile: Profile name (defaults to PROFILE_NAME env var or "profile")
        test_message: If True, send a test message to verify write access

    Returns:
        Dict with total, member_count, banned_count, health_score, results
    """
    return run_command(_check_all_bans)(
        channels=channels,
        profile=profile,
        test_message=test_message,
    )
