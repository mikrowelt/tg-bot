import random
import asyncio
from telethon import TelegramClient
from telethon.errors import FloodWaitError

from ..utils.logger import setup_logger
from .captcha import CaptchaSolver, CaptchaError
from .math_solver import MathSolver
from .pm import PMVerification, PMVerificationError

log = setup_logger("tg-bot.verification")


class VerificationError(Exception):
    """Raised when verification fails."""
    pass


class ButtonVerification:
    """
    Generic anti-bot verification handler.
    Handles: button clicks, math problems, image captchas, PM verification.

    IMPORTANT: Only performs ONE verification action per call to avoid account freezes.
    """

    def __init__(self, client: TelegramClient, captcha_api_key: str | None = None):
        self.client = client
        self.captcha_solver = CaptchaSolver(captcha_api_key)
        self.pm_verification = PMVerification(client)

    async def verify(self, channel_id: int, limit: int = 5) -> bool:
        """
        Scan channel messages and handle bot verification.
        Returns True if verification completed successfully.

        Only processes ONE verification action to avoid rate limits.
        """
        log.info(f"Scanning channel {channel_id} for verification bots...")

        try:
            bot_message = None
            bot_sender = None

            # Find the first bot message with verification
            async for message in self.client.iter_messages(channel_id, limit=limit):
                await asyncio.sleep(random.uniform(0.5, 1.5))

                sender = await message.get_sender()
                is_from_bot = sender and hasattr(sender, "bot") and sender.bot

                if is_from_bot:
                    bot_message = message
                    bot_sender = sender
                    break

            if not bot_message:
                log.info("No verification bot found")
                return True

            bot_name = bot_sender.first_name or "Unknown"
            bot_username = bot_sender.username or "unknown"
            log.info(f"Found bot: {bot_name} (@{bot_username})")

            # Try verification methods in order of priority
            # 1. Math problem (fastest, no external API)
            if bot_message.message:
                math_answer = MathSolver.solve(bot_message.message)
                if math_answer:
                    await asyncio.sleep(random.uniform(3, 6))
                    await bot_message.reply(math_answer)
                    log.info(f"Replied with math answer: {math_answer}")
                    return True

            # 2. Image captcha (requires API key)
            if bot_message.photo:
                log.info("Image captcha detected")
                try:
                    photo_bytes = await self.client.download_media(bot_message.photo, bytes)
                    captcha_answer = await self.captcha_solver.solve(photo_bytes)
                    await asyncio.sleep(random.uniform(3, 6))
                    await bot_message.reply(captcha_answer)
                    log.info("Replied with captcha answer")
                    return True
                except CaptchaError as e:
                    log.warning(f"Captcha solving failed: {e}")

            # 3. Button click (try callback buttons first, then URL)
            if bot_message.reply_markup and hasattr(bot_message.reply_markup, "rows"):
                rows = bot_message.reply_markup.rows
                if rows:
                    log.debug(f"Found {len(rows)} button row(s)")

                    # Find and click the first callback button only
                    for row in rows:
                        for button in row.buttons:
                            button_type = type(button).__name__

                            if button_type == "KeyboardButtonCallback":
                                await asyncio.sleep(random.uniform(3, 6))
                                try:
                                    result = await bot_message.click(data=button.data)
                                    result_msg = result.message if result else "OK"
                                    log.info(f"Clicked button '{button.text}': {result_msg}")
                                    # Wait for bot to process verification
                                    log.debug("Waiting for verification to process...")
                                    await asyncio.sleep(random.uniform(3, 5))
                                    return True
                                except FloodWaitError as e:
                                    log.warning(f"Rate limited clicking button, waiting {e.seconds}s")
                                    await asyncio.sleep(e.seconds + random.uniform(5, 10))
                                    raise VerificationError(f"Rate limited: {e.seconds}s")
                                except Exception as e:
                                    log.warning(f"Button click failed: {e}")
                                    # Continue to try other methods

                    # If no callback buttons worked, try URL buttons for PM verification
                    for row in rows:
                        for button in row.buttons:
                            button_type = type(button).__name__

                            if button_type == "KeyboardButtonUrl":
                                url = button.url
                                if "t.me/" in url and bot_sender.username:
                                    log.debug(f"URL button found, trying PM verification")
                                    try:
                                        await asyncio.sleep(random.uniform(2, 4))
                                        await self.pm_verification.verify(bot_sender.username)
                                        return True
                                    except PMVerificationError as e:
                                        log.warning(f"PM verification failed: {e}")

            log.info("Verification scan completed")
            return True

        except FloodWaitError as e:
            log.error(f"Rate limited, need to wait {e.seconds}s")
            raise VerificationError(f"Rate limited: wait {e.seconds} seconds")

        except Exception as e:
            log.error(f"Verification error: {e}")
            raise VerificationError(f"Verification failed: {e}")
