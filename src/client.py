import random
import asyncio
from dataclasses import dataclass
from telethon import TelegramClient, functions
from telethon.errors import (
    SessionPasswordNeededError,
    UserAlreadyParticipantError,
    FloodWaitError,
    ChatWriteForbiddenError,
    UserBannedInChannelError,
    ChannelPrivateError,
    ChatRestrictedError,
    SlowModeWaitError,
    ForbiddenError,
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


@dataclass
class SendResult:
    """Result of a send message operation."""
    ok: bool
    message_id: int | None = None
    error: str | None = None
    retryable: bool = True
    wait_seconds: int | None = None


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

    # ============ HEALTH CHECK ============

    async def health_check(self) -> dict:
        """
        Check if the client is healthy and ready to send messages.

        Returns a dict with:
            - ok: bool - True if all checks pass
            - connected: bool - TCP connection status
            - authorized: bool - User authorization status
            - user_id: int | None - Current user ID
            - username: str | None - Current username
            - restricted: bool - Whether account has restrictions
            - error: str | None - Error message if any check fails
        """
        result = {
            "ok": False,
            "connected": False,
            "authorized": False,
            "user_id": None,
            "username": None,
            "restricted": False,
            "error": None,
        }

        try:
            # Check if client exists
            if self._client is None:
                result["error"] = "Client not initialized"
                return result

            # Check connection
            if not self._client.is_connected():
                result["error"] = "Client not connected"
                return result
            result["connected"] = True

            # Check authorization
            if not await self._client.is_user_authorized():
                result["error"] = "User not authorized"
                return result
            result["authorized"] = True

            # Get user info
            me = await self._client.get_me()
            result["user_id"] = me.id
            result["username"] = me.username

            # Check for restrictions
            if me.restricted:
                result["restricted"] = True
                result["error"] = "Account is restricted"
                return result

            result["ok"] = True
            log.debug(f"Health check passed for user {me.id}")

        except Exception as e:
            result["error"] = str(e)
            log.warning(f"Health check failed: {e}")

        return result

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
    ) -> SendResult:
        """
        Send a message to a chat, channel, or user.
        Can also reply to a specific message.

        Returns SendResult with:
            - ok: True if message was sent
            - message_id: ID of sent message (if ok)
            - error: Error message (if not ok)
            - retryable: False for permanent errors (banned, no permissions)
            - wait_seconds: Seconds to wait before retry (for rate limits)
        """
        log.info(f"Sending message to: {target}")
        log.debug(f"Message text: {text[:50]}{'...' if len(text) > 50 else ''}")
        try:
            await asyncio.sleep(random.uniform(1, 3))
            msg = await self.client.send_message(target, text, reply_to=reply_to)
            log.info(f"Message sent successfully (id={msg.id})")
            return SendResult(ok=True, message_id=msg.id)

        except (ChatWriteForbiddenError, UserBannedInChannelError) as e:
            log.error(f"Banned or no write permission: {e}")
            return SendResult(
                ok=False,
                error="banned",
                retryable=False,
            )

        except ChannelPrivateError as e:
            log.error(f"Channel is private or deleted: {e}")
            return SendResult(
                ok=False,
                error="channel_private",
                retryable=False,
            )

        except ChatRestrictedError as e:
            log.error(f"Chat is restricted: {e}")
            return SendResult(
                ok=False,
                error="chat_restricted",
                retryable=False,
            )

        except ForbiddenError as e:
            log.error(f"Forbidden: {e}")
            return SendResult(
                ok=False,
                error="forbidden",
                retryable=False,
            )

        except FloodWaitError as e:
            log.warning(f"Rate limited for {e.seconds}s")
            return SendResult(
                ok=False,
                error="flood_wait",
                retryable=True,
                wait_seconds=e.seconds,
            )

        except SlowModeWaitError as e:
            log.warning(f"Slow mode: wait {e.seconds}s")
            return SendResult(
                ok=False,
                error="slow_mode",
                retryable=True,
                wait_seconds=e.seconds,
            )

        except Exception as e:
            log.error(f"Send failed: {e}")
            return SendResult(
                ok=False,
                error=str(e),
                retryable=True,
            )

    async def send_comment(self, channel: int | str, post_id: int, text: str) -> SendResult:
        """
        Send a comment to a channel post.
        Returns SendResult (same as send_message).
        """
        log.info(f"Sending comment to post {post_id} in {channel}")
        try:
            await asyncio.sleep(random.uniform(1, 3))
            msg = await self.client.send_message(channel, text, comment_to=post_id)
            log.info(f"Comment sent successfully (id={msg.id})")
            return SendResult(ok=True, message_id=msg.id)

        except (ChatWriteForbiddenError, UserBannedInChannelError) as e:
            log.error(f"Banned or no write permission: {e}")
            return SendResult(ok=False, error="banned", retryable=False)

        except ChannelPrivateError as e:
            log.error(f"Channel is private or deleted: {e}")
            return SendResult(ok=False, error="channel_private", retryable=False)

        except ChatRestrictedError as e:
            log.error(f"Chat is restricted: {e}")
            return SendResult(ok=False, error="chat_restricted", retryable=False)

        except ForbiddenError as e:
            log.error(f"Forbidden: {e}")
            return SendResult(ok=False, error="forbidden", retryable=False)

        except FloodWaitError as e:
            log.warning(f"Rate limited for {e.seconds}s")
            return SendResult(ok=False, error="flood_wait", retryable=True, wait_seconds=e.seconds)

        except SlowModeWaitError as e:
            log.warning(f"Slow mode: wait {e.seconds}s")
            return SendResult(ok=False, error="slow_mode", retryable=True, wait_seconds=e.seconds)

        except Exception as e:
            log.error(f"Comment failed: {e}")
            return SendResult(ok=False, error=str(e), retryable=True)

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
