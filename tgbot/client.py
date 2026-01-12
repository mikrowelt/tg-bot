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
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.photos import GetUserPhotosRequest, DeletePhotosRequest

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
        Update profile information. Supports partial updates - only provided
        fields will be changed, existing values are preserved.

        Args:
            first_name: New first name (None to keep current)
            last_name: New last name (None to keep current, "" to clear)
            about: New bio/about text (None to keep current, "" to clear)
            username: New username without @ (None to keep current)
            photo_path: Path to new profile photo

        Raises:
            ProfileUpdateError: If update fails
        """
        log.info("Updating profile...")
        try:
            # Update name and bio (with partial update support)
            if first_name is not None or last_name is not None or about is not None:
                # Fetch current profile to preserve unchanged fields
                me = await self.client.get_me()
                full_user = await self.client(GetFullUserRequest(me.id))
                current_about = full_user.full_user.about or ""

                # Use provided values or keep current
                new_first_name = first_name if first_name is not None else me.first_name
                new_last_name = last_name if last_name is not None else (me.last_name or "")
                new_about = about if about is not None else current_about

                log.debug(f"Setting name: {new_first_name} {new_last_name}")
                await self.client(UpdateProfileRequest(
                    first_name=new_first_name,
                    last_name=new_last_name,
                    about=new_about,
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
            if username is not None:
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
        """
        Get current profile information from Telegram.

        Returns:
            {
                "user_id": int,
                "first_name": str,
                "last_name": str | None,
                "username": str | None,
                "about": str | None,
                "phone": str,
                "photo": bytes | None,  # Profile photo as bytes, or None if no photo
            }
        """
        log.info("Fetching profile information...")

        # Get basic user info
        me = await self.client.get_me()

        # Get full user info (includes about/bio)
        full_user = await self.client(GetFullUserRequest(me.id))
        about = full_user.full_user.about

        # Download profile photo as bytes if exists
        photo_bytes = None
        if me.photo:
            log.debug("Downloading profile photo...")
            photo_bytes = await self.client.download_profile_photo(
                me, file=bytes
            )

        result = {
            "user_id": me.id,
            "first_name": me.first_name,
            "last_name": me.last_name,
            "username": me.username,
            "about": about,
            "phone": me.phone,
            "photo": photo_bytes,
        }

        log.info(f"Profile fetched for user {me.id} (@{me.username or 'no username'})")
        return result

    async def profile_health_check(
        self,
        expected_first_name: str | None = None,
        expected_last_name: str | None = None,
        expected_username: str | None = None,
        expected_about: str | None = None,
    ) -> dict:
        """
        Comprehensive profile health check.

        Checks:
        - Account is not frozen/blocked/restricted
        - Profile data matches expected values (if provided)

        Args:
            expected_first_name: Expected first name to verify against
            expected_last_name: Expected last name to verify against
            expected_username: Expected username to verify against
            expected_about: Expected bio/about to verify against

        Returns:
            {
                "ok": bool,  # True if all checks pass
                "account_status": {
                    "authorized": bool,
                    "restricted": bool,
                    "restriction_reason": str | None,
                    "deleted": bool,
                    "fake": bool,
                    "scam": bool,
                },
                "profile": {
                    "user_id": int,
                    "first_name": str,
                    "last_name": str | None,
                    "username": str | None,
                    "about": str | None,
                    "has_photo": bool,
                },
                "sync_status": {
                    "in_sync": bool,  # True if all expected values match
                    "mismatches": [{"field": str, "expected": str, "actual": str}, ...]
                },
                "errors": [str, ...]  # List of issues found
            }
        """
        log.info("Running profile health check...")

        result = {
            "ok": False,
            "account_status": {
                "authorized": False,
                "restricted": False,
                "restriction_reason": None,
                "deleted": False,
                "fake": False,
                "scam": False,
            },
            "profile": {
                "user_id": None,
                "first_name": None,
                "last_name": None,
                "username": None,
                "about": None,
                "has_photo": False,
            },
            "sync_status": {
                "in_sync": True,
                "mismatches": [],
            },
            "errors": [],
        }

        try:
            # Check authorization
            if not await self.client.is_user_authorized():
                result["errors"].append("Account not authorized")
                return result
            result["account_status"]["authorized"] = True

            # Get user info
            me = await self.client.get_me()
            result["profile"]["user_id"] = me.id

            # Check account flags
            if me.restricted:
                result["account_status"]["restricted"] = True
                if me.restriction_reason:
                    result["account_status"]["restriction_reason"] = me.restriction_reason
                result["errors"].append(f"Account is restricted: {me.restriction_reason or 'unknown reason'}")

            if me.deleted:
                result["account_status"]["deleted"] = True
                result["errors"].append("Account is deleted")

            if me.fake:
                result["account_status"]["fake"] = True
                result["errors"].append("Account is marked as fake")

            if me.scam:
                result["account_status"]["scam"] = True
                result["errors"].append("Account is marked as scam")

            # Get full profile info
            full_user = await self.client(GetFullUserRequest(me.id))
            about = full_user.full_user.about

            result["profile"]["first_name"] = me.first_name
            result["profile"]["last_name"] = me.last_name
            result["profile"]["username"] = me.username
            result["profile"]["about"] = about
            result["profile"]["has_photo"] = me.photo is not None

            # Check sync status if expected values provided
            mismatches = []

            if expected_first_name is not None and me.first_name != expected_first_name:
                mismatches.append({
                    "field": "first_name",
                    "expected": expected_first_name,
                    "actual": me.first_name,
                })

            if expected_last_name is not None and (me.last_name or "") != (expected_last_name or ""):
                mismatches.append({
                    "field": "last_name",
                    "expected": expected_last_name,
                    "actual": me.last_name,
                })

            if expected_username is not None and (me.username or "") != (expected_username or ""):
                mismatches.append({
                    "field": "username",
                    "expected": expected_username,
                    "actual": me.username,
                })

            if expected_about is not None and (about or "") != (expected_about or ""):
                mismatches.append({
                    "field": "about",
                    "expected": expected_about,
                    "actual": about,
                })

            if mismatches:
                result["sync_status"]["in_sync"] = False
                result["sync_status"]["mismatches"] = mismatches
                result["errors"].append(f"Profile out of sync: {len(mismatches)} field(s) mismatch")

            # Overall status
            result["ok"] = len(result["errors"]) == 0

            log.info(f"Profile health check: {'OK' if result['ok'] else 'ISSUES FOUND'}")

        except Exception as e:
            log.error(f"Profile health check failed: {e}")
            result["errors"].append(f"Check failed: {e}")

        return result

    async def delete_all_profile_photos(self) -> int:
        """
        Delete all profile photos from the account.

        Returns:
            Number of photos deleted
        """
        log.info("Deleting all profile photos...")

        try:
            # Get current user
            me = await self.client.get_me()

            # Fetch all photos with pagination
            all_photos = []
            offset = 0

            while True:
                result = await self.client(GetUserPhotosRequest(
                    user_id=me.id,
                    offset=offset,
                    max_id=0,
                    limit=100
                ))

                if not result.photos:
                    break

                all_photos.extend(result.photos)

                # Check if more photos available
                if hasattr(result, 'count'):
                    if len(all_photos) >= result.count:
                        break

                offset += 100
                await asyncio.sleep(0.5)  # Small delay between pagination requests

            if not all_photos:
                log.info("No profile photos to delete")
                return 0

            log.info(f"Found {len(all_photos)} profile photos to delete")

            # Delete all photos
            deleted = await self.client(DeletePhotosRequest(id=all_photos))
            deleted_count = len(deleted) if deleted else len(all_photos)

            log.info(f"Deleted {deleted_count} profile photos")
            return deleted_count

        except FloodWaitError as e:
            log.error(f"Rate limited for {e.seconds}s while deleting photos")
            raise ProfileUpdateError(f"Rate limited: wait {e.seconds} seconds")
        except Exception as e:
            log.error(f"Failed to delete profile photos: {e}")
            raise ProfileUpdateError(f"Failed to delete photos: {e}")

    async def upload_multiple_photos(
        self,
        photo_paths: list[str],
        delay_seconds: float = 3.0
    ) -> list[int]:
        """
        Upload multiple profile photos with delay between each upload.

        Args:
            photo_paths: List of paths to photo files
            delay_seconds: Delay between uploads (default 3s to avoid rate limits)

        Returns:
            List of photo IDs for uploaded photos
        """
        if not photo_paths:
            log.info("No photos to upload")
            return []

        log.info(f"Uploading {len(photo_paths)} profile photos with {delay_seconds}s delay...")
        uploaded_ids = []

        for i, photo_path in enumerate(photo_paths):
            try:
                log.debug(f"Uploading photo {i + 1}/{len(photo_paths)}: {photo_path}")

                result = await self.client(functions.photos.UploadProfilePhotoRequest(
                    file=await self.client.upload_file(photo_path)
                ))

                # Extract photo ID from result
                if hasattr(result, 'photo') and result.photo:
                    uploaded_ids.append(result.photo.id)
                    log.info(f"Uploaded photo {i + 1}/{len(photo_paths)} (id={result.photo.id})")
                else:
                    log.info(f"Uploaded photo {i + 1}/{len(photo_paths)}")

                # Delay between uploads (except after last one)
                if i < len(photo_paths) - 1:
                    log.debug(f"Waiting {delay_seconds}s before next upload...")
                    await asyncio.sleep(delay_seconds)

            except FloodWaitError as e:
                log.error(f"Rate limited for {e.seconds}s while uploading photo {i + 1}")
                raise ProfileUpdateError(f"Rate limited: wait {e.seconds} seconds")
            except Exception as e:
                log.error(f"Failed to upload photo {i + 1}: {e}")
                raise ProfileUpdateError(f"Failed to upload photo {photo_path}: {e}")

        log.info(f"Successfully uploaded {len(uploaded_ids)} photos")
        return uploaded_ids
