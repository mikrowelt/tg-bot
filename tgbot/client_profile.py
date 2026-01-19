"""
Profile operations mixin for TgBot.

Extracted from client.py to reduce file size.
"""
import asyncio
import random

from telethon import functions
from telethon.errors import (
    FloodWaitError,
    UsernameOccupiedError,
    UsernameInvalidError,
    UsernameNotModifiedError,
)
from telethon.tl.functions.account import UpdateProfileRequest, UpdateUsernameRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.photos import GetUserPhotosRequest, DeletePhotosRequest
from telethon.tl.types import Channel, Chat

from .utils.logger import setup_logger
from .utils.metrics import record_profile_update, record_error

log = setup_logger("tg-bot.client.profile")


class TgBotError(Exception):
    """Base exception for TgBot errors."""
    pass


class ProfileUpdateError(TgBotError):
    """Raised when profile update fails."""
    pass


class ProfileMixin:
    """Mixin providing profile operations for TgBot."""

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
                record_profile_update("name_bio", "success")
                log.info("Profile name/bio updated")
                await asyncio.sleep(random.uniform(3, 7))

            # Update photo
            if photo_path:
                log.debug(f"Uploading photo: {photo_path}")
                await self.client(functions.photos.UploadProfilePhotoRequest(
                    file=await self.client.upload_file(photo_path)
                ))
                record_profile_update("photo", "success")
                log.info("Profile photo updated")
                await asyncio.sleep(random.uniform(3, 7))

            # Update username
            if username is not None:
                log.debug(f"Setting username: @{username}")
                await self.client(UpdateUsernameRequest(username=username))
                record_profile_update("username", "success")
                log.info(f"Username set to @{username}")

        except FloodWaitError as e:
            log.error(f"Rate limited for {e.seconds}s")
            record_profile_update("profile", "rate_limited")
            raise ProfileUpdateError(f"Rate limited: wait {e.seconds} seconds")
        except Exception as e:
            log.error(f"Profile update failed: {e}")
            record_profile_update("profile", "error")
            record_error(type(e).__name__, "profile_update")
            raise ProfileUpdateError(f"Failed to update profile: {e}")

    async def set_username(self, username: str, max_attempts: int = 10) -> dict:
        """
        Set username with automatic retry if taken.

        If the username is already taken, tries variations by appending numbers
        until a unique one is found.

        Args:
            username: Desired username (without @)
            max_attempts: Maximum number of variations to try

        Returns:
            {
                "success": bool,
                "username": str - The actual username set (may differ from requested),
                "attempts": int - Number of attempts made,
                "error": str | None
            }
        """
        result = {
            "success": False,
            "username": None,
            "original_username": username,
            "attempts": 0,
            "error": None,
        }

        # Clean username - remove @ if present, lowercase
        username = username.lstrip("@").lower()

        # Generate username variations
        variations = [username]
        for i in range(1, max_attempts):
            # Try with numbers: username1, username2, etc.
            variations.append(f"{username}{i}")
            # Also try with random suffix for more uniqueness
            if i > 5:
                import random as rnd
                variations.append(f"{username}{rnd.randint(100, 999)}")

        for attempt, try_username in enumerate(variations[:max_attempts], 1):
            result["attempts"] = attempt
            try:
                log.debug(f"Trying username: @{try_username} (attempt {attempt})")
                await self.client(UpdateUsernameRequest(username=try_username))
                result["success"] = True
                result["username"] = try_username
                record_profile_update("username", "success")
                log.info(f"Username set to @{try_username}")
                return result

            except UsernameOccupiedError:
                log.debug(f"Username @{try_username} is taken, trying next variation")
                await asyncio.sleep(2)  # Delay between attempts to avoid rate limit
                continue

            except UsernameNotModifiedError:
                # Username is the same as current - that's fine
                result["success"] = True
                result["username"] = try_username
                log.info(f"Username @{try_username} is already set")
                return result

            except UsernameInvalidError as e:
                log.warning(f"Username @{try_username} is invalid: {e}")
                await asyncio.sleep(2)  # Delay between attempts to avoid rate limit
                continue

            except FloodWaitError as e:
                # If we hit rate limit, wait and continue (don't return immediately)
                if e.seconds <= 30:
                    log.warning(f"Rate limited for {e.seconds}s, waiting...")
                    await asyncio.sleep(e.seconds + 1)
                    continue
                else:
                    result["error"] = f"Rate limited: wait {e.seconds} seconds"
                    log.error(result["error"])
                    return result

            except Exception as e:
                result["error"] = str(e)
                record_profile_update("username", "error")
                record_error(type(e).__name__, "set_username")
                log.error(f"Failed to set username: {e}")
                return result

        result["error"] = f"Could not find available username after {max_attempts} attempts"
        record_profile_update("username", "exhausted")
        log.warning(result["error"])
        return result

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

    async def get_joined_channels(self) -> list[dict]:
        """
        Get list of all channels and groups the account has joined.

        Returns:
            List of dicts with channel/group info:
            [
                {
                    "id": int,
                    "title": str,
                    "username": str | None,
                    "type": "channel" | "group" | "supergroup",
                    "participants_count": int | None,
                }
            ]
        """
        log.info("Fetching joined channels and groups...")

        channels = []

        try:
            # Use iter_dialogs which handles pagination automatically
            async for dialog in self.client.iter_dialogs():
                entity = dialog.entity

                # Only include channels and groups, not private chats
                if isinstance(entity, Channel):
                    channel_type = "channel" if entity.broadcast else "supergroup"
                    channels.append({
                        "id": entity.id,
                        "title": entity.title,
                        "username": entity.username,
                        "type": channel_type,
                        "participants_count": getattr(entity, 'participants_count', None),
                    })
                elif isinstance(entity, Chat):
                    channels.append({
                        "id": entity.id,
                        "title": entity.title,
                        "username": None,
                        "type": "group",
                        "participants_count": getattr(entity, 'participants_count', None),
                    })

            log.info(f"Found {len(channels)} joined channels/groups")
            return channels

        except FloodWaitError as e:
            log.error(f"Rate limited for {e.seconds}s while fetching dialogs")
            raise TgBotError(f"Rate limited: wait {e.seconds} seconds")
        except Exception as e:
            log.error(f"Failed to fetch joined channels: {e}")
            raise TgBotError(f"Failed to fetch channels: {e}")

    async def get_profile_photos(self, download_path: str | None = None) -> list[dict]:
        """
        Get all profile photos from the account.

        Args:
            download_path: Optional directory to download photos to.
                          If provided, photos will be saved as files.

        Returns:
            List of dicts with photo info:
            [
                {
                    "id": int,
                    "date": datetime,
                    "file_path": str | None,  # Only if download_path provided
                    "bytes": bytes | None,    # Only if download_path not provided
                }
            ]
        """
        log.info("Fetching profile photos...")

        try:
            me = await self.client.get_me()
            photos = []
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

                for photo in result.photos:
                    photo_info = {
                        "id": photo.id,
                        "date": photo.date,
                        "file_path": None,
                        "bytes": None,
                    }

                    # Download the photo
                    if download_path:
                        import os
                        file_path = os.path.join(download_path, f"photo_{photo.id}.jpg")
                        await self.client.download_media(photo, file=file_path)
                        photo_info["file_path"] = file_path
                        log.debug(f"Downloaded photo {photo.id} to {file_path}")
                    else:
                        photo_bytes = await self.client.download_media(photo, file=bytes)
                        photo_info["bytes"] = photo_bytes
                        log.debug(f"Downloaded photo {photo.id} as bytes")

                    photos.append(photo_info)

                # Check if more photos available
                if hasattr(result, 'count'):
                    if len(photos) >= result.count:
                        break

                offset += 100
                await asyncio.sleep(0.5)

            log.info(f"Found {len(photos)} profile photos")
            return photos

        except FloodWaitError as e:
            log.error(f"Rate limited for {e.seconds}s while fetching photos")
            raise TgBotError(f"Rate limited: wait {e.seconds} seconds")
        except Exception as e:
            log.error(f"Failed to fetch profile photos: {e}")
            raise TgBotError(f"Failed to fetch photos: {e}")
