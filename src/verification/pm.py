import random
import asyncio
from telethon import TelegramClient
from telethon.errors import FloodWaitError

from ..utils.logger import setup_logger

log = setup_logger("tg-bot.verification.pm")


class PMVerificationError(Exception):
    """Raised when PM verification fails."""
    pass


class PMVerification:
    """Handles PM-based bot verification."""

    def __init__(self, client: TelegramClient):
        self.client = client

    async def verify(self, bot_username: str) -> bool:
        """
        Send /start to a bot and click any verification buttons.
        Returns True if successful.
        """
        try:
            log.info(f"Starting PM verification with @{bot_username}")
            await asyncio.sleep(random.uniform(2, 4))

            # Get bot entity
            log.debug(f"Resolving bot entity: @{bot_username}")
            bot_entity = await self.client.get_entity(bot_username)

            # Send /start command
            await asyncio.sleep(random.uniform(2, 4))
            await self.client.send_message(bot_entity, "/start")
            log.info(f"Sent /start to @{bot_username}")

            # Wait for response and check for buttons
            await asyncio.sleep(random.uniform(4, 7))
            async for message in self.client.iter_messages(bot_entity, limit=3):
                if message.reply_markup and hasattr(message.reply_markup, "rows"):
                    rows = message.reply_markup.rows
                    if rows and rows[0].buttons:
                        log.debug("Found reply markup, clicking first button")
                        await asyncio.sleep(random.uniform(3, 5))
                        # Click using button data for more reliability
                        first_button = rows[0].buttons[0]
                        if hasattr(first_button, "data"):
                            await message.click(data=first_button.data)
                        else:
                            await message.click(0)
                        log.info("PM verification button clicked")
                        return True

            log.info("PM verification completed (no buttons found)")
            return True

        except FloodWaitError as e:
            log.warning(f"Rate limited in PM verification, need to wait {e.seconds}s")
            raise PMVerificationError(f"Rate limited: wait {e.seconds} seconds")

        except Exception as e:
            log.error(f"PM verification failed: {e}")
            raise PMVerificationError(f"PM verification failed: {e}")
