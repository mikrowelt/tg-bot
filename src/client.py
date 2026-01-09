import random
import asyncio
from telethon import TelegramClient, functions
from telethon.errors import (
    SessionPasswordNeededError,
    UserAlreadyParticipantError,
    FloodWaitError,
)
from telethon.tl.functions.account import UpdateProfileRequest, UpdateUsernameRequest
from telethon.tl.functions.messages import ImportChatInviteRequest, CheckChatInviteRequest

from .utils.config import Config
from .utils.logger import setup_logger
from .verification import ButtonVerification

log = setup_logger("tg-bot.client")


class TgBotError(Exception):
    """Base exception for TgBot errors."""
    pass


class JoinChannelError(TgBotError):
    """Raised when joining a channel fails."""
    pass


class SendMessageError(TgBotError):
    """Raised when sending a message fails."""
    pass


class ProfileUpdateError(TgBotError):
    """Raised when profile update fails."""
    pass


class TgBot:
    """Telegram bot client wrapper."""

    def __init__(self, config: Config):
        self.config = config
        self._client: TelegramClient | None = None
        self._verification: ButtonVerification | None = None

    @property
    def client(self) -> TelegramClient:
        if self._client is None:
            raise TgBotError("Client not initialized. Call connect() first.")
        return self._client

    @property
    def verification(self) -> ButtonVerification:
        if self._verification is None:
            self._verification = ButtonVerification(
                self.client, self.config.captcha_api_key
            )
        return self._verification

    async def connect(self) -> None:
        """Connect to Telegram and authenticate."""
        log.info("Connecting to Telegram...")
        proxy = self.config.proxy.to_tuple() if self.config.proxy else None

        if proxy:
            log.debug(f"Using proxy: {self.config.proxy}")

        self._client = TelegramClient(
            str(self.config.session_path),
            self.config.app_id,
            self.config.app_hash,
            proxy=proxy,
            device_model=self.config.device,
            system_version=self.config.sdk,
            app_version=self.config.app_version,
            lang_code=self.config.lang_pack,
        )

        await self._client.connect()
        log.debug("TCP connection established")

        if not await self._client.is_user_authorized():
            log.info("Authorization required")
            phone = "+" + self.config.phone
            await self._client.send_code_request(phone)
            log.info(f"Code sent to {phone}")
            try:
                code = input("Enter the code you received: ")
                await self._client.sign_in(phone, code)
                log.info("Signed in with code")
            except SessionPasswordNeededError:
                if not self.config.two_fa:
                    log.error("2FA required but not configured")
                    raise TgBotError("2FA required but not configured in profile")
                await self._client.sign_in(password=self.config.two_fa)
                log.info("Signed in with 2FA")

        me = await self._client.get_me()
        log.info(f"Connected as: {me.first_name} (@{me.username or 'no username'})")

    async def disconnect(self) -> None:
        """Disconnect from Telegram."""
        if self._client:
            await self._client.disconnect()
            self._client = None
            self._verification = None
            log.info("Disconnected from Telegram")

    async def __aenter__(self) -> "TgBot":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.disconnect()

    # ============ CHANNEL OPERATIONS ============

    async def join_channel(self, channel_link: str, verify: bool = True) -> int:
        """
        Join a channel and optionally pass bot verification.
        Returns the channel ID.
        Raises JoinChannelError on failure.
        """
        log.info(f"Joining channel: {channel_link}")
        channel_id = None

        try:
            if "/+" in channel_link or "joinchat" in channel_link:
                invite_hash = channel_link.split("/")[-1].replace("+", "")
                log.debug(f"Using invite hash: {invite_hash}")
                await asyncio.sleep(random.uniform(1, 3))
                result = await self.client(ImportChatInviteRequest(invite_hash))
                channel_id = result.chats[0].id
                log.info(f"Joined private channel: {channel_id}")
            else:
                username = channel_link.split("/")[-1]
                log.debug(f"Joining public channel: @{username}")
                entity = await self.client.get_entity(username)
                await asyncio.sleep(random.uniform(2, 5))
                await self.client(functions.channels.JoinChannelRequest(entity))
                channel_id = entity.id
                log.info(f"Joined public channel: {channel_id}")

        except UserAlreadyParticipantError:
            log.info("Already a member, fetching channel ID")
            await asyncio.sleep(random.uniform(1, 2))
            channel_id = await self._get_channel_id(channel_link)

        except FloodWaitError as e:
            log.error(f"Rate limited for {e.seconds}s")
            raise JoinChannelError(f"Rate limited: wait {e.seconds} seconds")

        except Exception as e:
            log.error(f"Join failed: {e}")
            raise JoinChannelError(f"Failed to join channel: {e}")

        if channel_id is None:
            log.error("Could not determine channel ID")
            raise JoinChannelError("Could not determine channel ID")

        # Run verification if requested
        if verify:
            log.info("Starting bot verification...")
            await asyncio.sleep(random.uniform(3, 7))
            await self.verification.verify(channel_id)
            # Extra wait for permissions to propagate
            log.debug("Waiting for permissions to update...")
            await asyncio.sleep(random.uniform(2, 4))

        return channel_id

    async def _get_channel_id(self, channel_link: str) -> int | None:
        """Get channel ID for a channel we're already a member of."""
        try:
            if "/+" in channel_link or "joinchat" in channel_link:
                invite_hash = channel_link.split("/")[-1].replace("+", "")
                result = await self.client(CheckChatInviteRequest(invite_hash))
                if hasattr(result, "chat"):
                    return result.chat.id
            else:
                username = channel_link.split("/")[-1]
                entity = await self.client.get_entity(username)
                return entity.id
        except Exception as e:
            log.warning(f"Failed to get channel ID: {e}")
            return None

    # ============ MESSAGE OPERATIONS ============

    async def send_message(
        self,
        target: int | str,
        text: str,
        reply_to: int | None = None,
    ) -> None:
        """
        Send a message to a chat, channel, or user.
        Can also reply to a specific message (for channel comments).
        Raises SendMessageError on failure.
        """
        log.info(f"Sending message to: {target}")
        log.debug(f"Message text: {text[:50]}{'...' if len(text) > 50 else ''}")
        try:
            await asyncio.sleep(random.uniform(1, 3))
            await self.client.send_message(target, text, reply_to=reply_to)
            log.info("Message sent successfully")
        except FloodWaitError as e:
            log.error(f"Rate limited for {e.seconds}s")
            raise SendMessageError(f"Rate limited: wait {e.seconds} seconds")
        except Exception as e:
            log.error(f"Send failed: {e}")
            raise SendMessageError(f"Failed to send message: {e}")

    async def send_comment(self, channel: int | str, post_id: int, text: str) -> None:
        """
        Send a comment to a channel post.
        Raises SendMessageError on failure.
        """
        log.info(f"Sending comment to post {post_id} in {channel}")
        try:
            await asyncio.sleep(random.uniform(1, 3))
            await self.client.send_message(channel, text, comment_to=post_id)
            log.info("Comment sent successfully")
        except FloodWaitError as e:
            log.error(f"Rate limited for {e.seconds}s")
            raise SendMessageError(f"Rate limited: wait {e.seconds} seconds")
        except Exception as e:
            log.error(f"Comment failed: {e}")
            raise SendMessageError(f"Failed to send comment: {e}")

    # ============ PROFILE OPERATIONS ============

    async def change_profile(
        self,
        first_name: str | None = None,
        last_name: str | None = None,
        about: str | None = None,
        username: str | None = None,
        photo_path: str | None = None,
    ) -> None:
        """
        Update profile information.
        Raises ProfileUpdateError on failure.
        """
        log.info("Updating profile...")
        try:
            # Update name and bio
            if first_name or last_name or about:
                log.debug(f"Setting name: {first_name} {last_name}")
                await self.client(UpdateProfileRequest(
                    first_name=first_name or "",
                    last_name=last_name or "",
                    about=about or "",
                ))
                log.info("Profile name/bio updated")
                await asyncio.sleep(random.uniform(3, 7))

            # Update photo
            if photo_path:
                log.debug(f"Uploading photo: {photo_path}")
                await self.client(functions.photos.UploadProfilePhotoRequest(
                    file=await self.client.upload_file(photo_path)
                ))
                log.info("Profile photo updated")
                await asyncio.sleep(random.uniform(3, 7))

            # Update username
            if username:
                log.debug(f"Setting username: @{username}")
                await self.client(UpdateUsernameRequest(username=username))
                log.info(f"Username set to @{username}")

        except FloodWaitError as e:
            log.error(f"Rate limited for {e.seconds}s")
            raise ProfileUpdateError(f"Rate limited: wait {e.seconds} seconds")
        except Exception as e:
            log.error(f"Profile update failed: {e}")
            raise ProfileUpdateError(f"Failed to update profile: {e}")

    async def get_profile(self) -> dict:
        """Get current user profile information."""
        me = await self.client.get_me()
        return me.to_dict()
