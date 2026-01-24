"""
Channel operations mixin for TgBot.

This module provides channel-related operations:
- join_channel
- leave_channel
- _join_linked_discussion
- _get_channel_id
"""
import random
import asyncio
from telethon import functions
from telethon.errors import (
    UserAlreadyParticipantError,
    FloodWaitError,
)
from telethon.tl.functions.messages import ImportChatInviteRequest, CheckChatInviteRequest
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.types import Channel, Chat

from .utils.logger import setup_logger
from .utils.metrics import (
    record_channel_join,
    record_rate_limit,
    record_error,
    record_verification,
)
from .utils.constants import (
    WAIT_NORMAL,
    WAIT_SHORT,
    WAIT_MEDIUM,
    WAIT_MEDIUM_LONG,
    WAIT_PROFILE,
    random_wait,
)

log = setup_logger("tg-bot.channels")


def extract_telegram_username(link: str) -> str:
    """
    Extract username from various Telegram link formats.

    Handles:
    - https://t.me/username
    - http://t.me/username
    - t.me/username
    - @username
    - username
    - Links with trailing slashes, query params, etc.

    Returns the clean username suitable for Telegram API calls.
    """
    if not link:
        return link

    # Strip whitespace
    link = link.strip()

    # Remove protocol
    if link.startswith("https://"):
        link = link[8:]
    elif link.startswith("http://"):
        link = link[7:]

    # Remove t.me/ prefix (handles both t.me/ and www.t.me/)
    if link.startswith("www."):
        link = link[4:]
    if link.startswith("t.me/"):
        link = link[5:]
    elif link.startswith("telegram.me/"):
        link = link[12:]

    # Remove @ prefix
    link = link.lstrip("@")

    # Remove trailing slashes
    link = link.rstrip("/")

    # Remove query parameters
    if "?" in link:
        link = link.split("?")[0]

    # Remove hash fragments
    if "#" in link:
        link = link.split("#")[0]

    # Handle cases like "channel/" where there might be path segments
    # Take only the first path segment (the username)
    if "/" in link:
        link = link.split("/")[0]

    return link


class ChannelsMixin:
    """Mixin providing channel operations for TgBot."""

    async def join_channel(
        self,
        channel_link: str,
        verify: bool = True,
        use_ai_verification: bool = True,
        verification_wait_seconds: float = 5.0,
    ) -> int:
        """
        Join a channel and optionally pass bot verification.

        Args:
            channel_link: Channel link or username
            verify: Whether to run verification after joining
            use_ai_verification: Use AI agent for verification (requires anthropic_api_key)
            verification_wait_seconds: How long to wait before checking for verification

        Returns the channel ID.
        Raises JoinChannelError on failure.
        """
        from .client import JoinChannelError  # Avoid circular import

        log.info(f"Joining channel: {channel_link}")
        channel_id = None

        try:
            if "/+" in channel_link or "joinchat" in channel_link:
                invite_hash = channel_link.split("/")[-1].replace("+", "")
                log.debug(f"Using invite hash: {invite_hash}")
                await asyncio.sleep(random_wait(WAIT_NORMAL))
                result = await self.client(ImportChatInviteRequest(invite_hash))
                channel_id = result.chats[0].id
                record_channel_join("success")
                log.info(f"Joined private channel: {channel_id}")
            else:
                # Extract username from various link formats
                username = extract_telegram_username(channel_link)
                log.debug(f"Joining public channel: @{username}")
                entity = await self.client.get_entity(username)
                await asyncio.sleep(random_wait(WAIT_MEDIUM_LONG))
                await self.client(functions.channels.JoinChannelRequest(entity))
                channel_id = entity.id
                record_channel_join("success")
                log.info(f"Joined public channel: {channel_id}")

        except UserAlreadyParticipantError:
            log.info("Already a member, fetching channel ID")
            record_channel_join("already_member")
            await asyncio.sleep(random_wait(WAIT_SHORT))
            channel_id = await self._get_channel_id(channel_link)

        except FloodWaitError as e:
            log.error(f"Rate limited for {e.seconds}s")
            record_channel_join("rate_limited")
            record_rate_limit("join_channel", e.seconds)
            raise JoinChannelError(f"Rate limited: wait {e.seconds} seconds")

        except Exception as e:
            log.error(f"Join failed: {e}")
            record_channel_join("error")
            record_error(type(e).__name__, "join_channel")
            raise JoinChannelError(f"Failed to join channel: {e}")

        if channel_id is None:
            log.error("Could not determine channel ID")
            raise JoinChannelError("Could not determine channel ID")

        # Try to join linked discussion group (needed for commenting)
        discussion_group_id = await self._join_linked_discussion(channel_id)
        if discussion_group_id:
            log.info(f"Also joined linked discussion group: {discussion_group_id}")

        # Run verification if requested
        if verify:
            log.info("Starting bot verification...")

            # Try AI verification first if available
            if use_ai_verification and self.ai_verification:
                log.info("Using AI verification agent...")

                # Check for verification in channel
                result = await self.ai_verification.check_and_handle_verification(
                    chat_id=channel_id,
                    context="after_join",
                    wait_seconds=verification_wait_seconds,
                )

                if result.action_taken:
                    log.info(f"AI verification handled: {result.action_taken} (cached: {result.cached})")
                    record_verification("ai_channel", "success")

                # Also check for verification in discussion group if we joined one
                if discussion_group_id:
                    log.info("Checking verification in discussion group...")
                    disc_result = await self.ai_verification.check_and_handle_verification(
                        chat_id=discussion_group_id,
                        context="after_join_discussion",
                        wait_seconds=verification_wait_seconds,
                    )

                    if disc_result.action_taken:
                        log.info(f"Discussion group verification handled: {disc_result.action_taken} (cached: {disc_result.cached})")
                        record_verification("ai_discussion", "success")

                # Check for verification in post comments
                log.info("Checking verification in post comments...")
                comments_result = await self.ai_verification.check_post_comments_verification(
                    channel_id=channel_id,
                    discussion_group_id=discussion_group_id,
                    wait_seconds=verification_wait_seconds,
                )

                if comments_result.action_taken:
                    log.info(f"Post comments verification handled: {comments_result.action_taken} (cached: {comments_result.cached})")
                    record_verification("ai_comments", "success")

                # Also check for DM verification
                dm_result = await self.ai_verification.check_dm_verification(
                    wait_seconds=verification_wait_seconds
                )

                if dm_result.action_taken:
                    log.info(f"AI DM verification handled: {dm_result.action_taken}")
                    record_verification("ai_dm", "success")

            else:
                # Fall back to legacy verification
                await asyncio.sleep(random_wait(WAIT_PROFILE))
                await self.verification.verify(channel_id)
                if discussion_group_id:
                    await asyncio.sleep(random_wait(WAIT_MEDIUM))
                    await self.verification.verify(discussion_group_id)

            # Extra wait for permissions to propagate
            log.debug("Waiting for permissions to update...")
            await asyncio.sleep(random_wait(WAIT_MEDIUM))

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
                username = extract_telegram_username(channel_link)
                entity = await self.client.get_entity(username)
                return entity.id
        except Exception as e:
            log.warning(f"Failed to get channel ID: {e}")
            return None

    async def _join_linked_discussion(self, channel_id: int) -> int | None:
        """
        Join the linked discussion group of a channel if it exists.
        This is needed to be able to post comments on channel posts.

        Returns the discussion group ID if joined, None otherwise.
        """
        try:
            # Get full channel info to find linked discussion group
            entity = await self.client.get_entity(channel_id)
            if not isinstance(entity, Channel):
                return None

            full_channel = await self.client(GetFullChannelRequest(entity))

            # Check if there's a linked chat (discussion group)
            linked_chat_id = getattr(full_channel.full_chat, 'linked_chat_id', None)
            if not linked_chat_id:
                log.debug(f"Channel {channel_id} has no linked discussion group")
                return None

            log.info(f"Found linked discussion group: {linked_chat_id}")

            # Try to join the discussion group
            try:
                discussion_entity = await self.client.get_entity(linked_chat_id)
                await asyncio.sleep(random_wait(WAIT_NORMAL))
                await self.client(functions.channels.JoinChannelRequest(discussion_entity))
                log.info(f"Joined discussion group: {linked_chat_id}")
                return linked_chat_id

            except UserAlreadyParticipantError:
                log.debug(f"Already a member of discussion group {linked_chat_id}")
                return linked_chat_id

            except Exception as e:
                log.warning(f"Could not join discussion group {linked_chat_id}: {e}")
                return None

        except Exception as e:
            log.debug(f"Could not get linked discussion for channel {channel_id}: {e}")
            return None

    async def leave_channel(self, channel: int | str) -> dict:
        """
        Leave a channel or group.

        Args:
            channel: Channel/group ID, username, or invite link

        Returns dict with:
            - success: bool
            - channel_id: int (if success)
            - error: str (if failed)
        """
        log.info(f"Leaving channel: {channel}")

        try:
            # Get entity from ID, username, or link
            if isinstance(channel, str):
                if "/+" in channel or "joinchat" in channel:
                    # Private channel - try CheckChatInviteRequest first
                    invite_hash = channel.split("/")[-1].replace("+", "")
                    try:
                        result = await self.client(CheckChatInviteRequest(invite_hash))
                        if hasattr(result, "chat"):
                            entity = result.chat
                        else:
                            # Not a member yet, can't leave
                            return {"success": False, "error": "Not a member of this channel"}
                    except Exception as e:
                        # CheckChatInviteRequest can fail, try to find in dialogs
                        log.warning(f"CheckChatInviteRequest failed: {e}, searching dialogs...")
                        entity = None
                        async for dialog in self.client.iter_dialogs():
                            # Match by invite link hash in the entity
                            if hasattr(dialog.entity, 'id'):
                                entity = dialog.entity
                                # We can't easily match invite hash to dialog, so this is a fallback
                                # The caller should use channel ID instead of invite link when leaving
                                break
                        if entity is None:
                            return {"success": False, "error": "Could not find channel in dialogs"}
                else:
                    # Public channel - get by username
                    username = extract_telegram_username(channel)
                    entity = await self.client.get_entity(username)
            else:
                # Direct ID
                entity = await self.client.get_entity(channel)

            channel_id = entity.id

            # Leave the channel/group
            await asyncio.sleep(random_wait(WAIT_SHORT))

            if isinstance(entity, Channel):
                # For channels/supergroups
                await self.client(functions.channels.LeaveChannelRequest(entity))
            elif isinstance(entity, Chat):
                # For regular groups - need to delete self from chat
                me = await self.client.get_me()
                await self.client(functions.messages.DeleteChatUserRequest(
                    chat_id=entity.id,
                    user_id=me.id
                ))
            else:
                return {"success": False, "error": f"Unknown entity type: {type(entity)}"}

            log.info(f"Left channel: {channel_id}")

            return {"success": True, "channel_id": channel_id}

        except Exception as e:
            log.error(f"Failed to leave channel: {e}")
            return {"success": False, "error": str(e)}
