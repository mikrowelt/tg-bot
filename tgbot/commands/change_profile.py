import asyncio
import sys

from ..utils.config import Config, ConfigError
from ..utils.logger import setup_logger
from ..client import TgBot, ProfileUpdateError

log = setup_logger("tg-bot.cmd.profile")


async def _change_profile(
    profile: str | None,
    first_name: str | None,
    last_name: str | None,
    about: str | None,
    username: str | None,
    photo: str | None,
) -> None:
    """Internal async implementation."""
    config = Config.load(profile)

    async with TgBot(config) as bot:
        await bot.change_profile(
            first_name=first_name,
            last_name=last_name,
            about=about,
            username=username,
            photo_path=photo,
        )


def change_profile(
    profile: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    about: str | None = None,
    username: str | None = None,
    photo: str | None = None,
) -> None:
    """
    Change Telegram profile information.

    Args:
        profile: Profile name (defaults to PROFILE_NAME env var or "profile")
        first_name: New first name
        last_name: New last name
        about: New bio/about text
        username: New username (without @)
        photo: Path to new profile photo
    """
    try:
        asyncio.run(_change_profile(
            profile=profile,
            first_name=first_name,
            last_name=last_name,
            about=about,
            username=username,
            photo=photo,
        ))
        log.info("Profile update completed successfully")
    except ConfigError as e:
        log.error(f"Configuration error: {e}")
        sys.exit(1)
    except ProfileUpdateError as e:
        log.error(f"Profile update failed: {e}")
        sys.exit(1)
    except Exception as e:
        log.error(f"Unexpected error: {e}")
        sys.exit(1)
