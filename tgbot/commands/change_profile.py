"""Change profile command."""

from ..utils.config import Config
from ..utils.logger import setup_logger
from ..client import TgBot, ProfileUpdateError
from .base import run_command

log = setup_logger("tg-bot.cmd.profile")


async def _change_profile(
    profile: str | None,
    first_name: str | None,
    last_name: str | None,
    about: str | None,
    username: str | None,
    photo: str | None,
) -> dict:
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

    log.info("Profile update completed successfully")
    return {"success": True}


def change_profile(
    profile: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    about: str | None = None,
    username: str | None = None,
    photo: str | None = None,
) -> dict | None:
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
    return run_command(
        _change_profile,
        error_types=(ProfileUpdateError,),
        print_result=False,
    )(
        profile=profile,
        first_name=first_name,
        last_name=last_name,
        about=about,
        username=username,
        photo=photo,
    )
