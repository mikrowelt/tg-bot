"""Get profile command."""

import base64

from ..utils.config import Config
from ..utils.logger import setup_logger
from ..client import TgBot
from .base import run_command

log = setup_logger("tg-bot.cmd.get_profile")


async def _get_profile(profile: str | None, include_photo: bool) -> dict:
    """Internal async implementation."""
    config = Config.load(profile)

    async with TgBot(config) as bot:
        result = await bot.get_profile()

        # Handle photo bytes for JSON serialization
        if result.get("photo") is not None:
            if include_photo:
                # Base64 encode photo for JSON output
                result["photo"] = base64.b64encode(result["photo"]).decode("utf-8")
                result["photo_encoding"] = "base64"
            else:
                # Just indicate photo exists
                result["photo"] = True
                result["photo_encoding"] = None
        else:
            result["photo_encoding"] = None

        return result


def get_profile(profile: str | None = None, include_photo: bool = False) -> dict | None:
    """
    Get current Telegram profile information.

    Args:
        profile: Profile name (defaults to PROFILE_NAME env var or "profile")
        include_photo: If True, include base64-encoded profile photo in response

    Returns:
        Dict with current profile data from Telegram:
            - user_id: int
            - first_name: str
            - last_name: str | None
            - username: str | None
            - about: str | None
            - phone: str
            - photo: base64 str (if include_photo) | bool (photo exists) | None
            - photo_encoding: "base64" | None
    """
    return run_command(_get_profile)(profile=profile, include_photo=include_photo)
