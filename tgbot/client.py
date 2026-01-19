"""
Telegram bot client wrapper.

This module provides the TgBot class for interacting with Telegram.
Profile operations are provided via ProfileMixin from client_profile.py.
"""
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
from telethon.tl.functions.account import GetAuthorizationsRequest, ResetAuthorizationRequest
from telethon.tl.functions.messages import ImportChatInviteRequest, CheckChatInviteRequest
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.types import ReactionEmoji
from telethon.tl.types import Channel, Chat

from .utils.config import Config
from .utils.logger import setup_logger
from .utils.metrics import (
    record_channel_join,
    record_message_sent,
    record_rate_limit,
    record_error,
    record_verification,
)
from .verification import ButtonVerification

# Import profile mixin
from .client_profile import ProfileMixin, TgBotError, ProfileUpdateError

# Import AI verification (optional - may not be available if anthropic not installed)
try:
    from .verification import AIVerificationAgent, VerificationResult
    AI_VERIFICATION_AVAILABLE = True
except ImportError:
    AI_VERIFICATION_AVAILABLE = False
    AIVerificationAgent = None
    VerificationResult = None

log = setup_logger("tg-bot.client")


class JoinChannelError(TgBotError):
    """Raised when joining a channel fails."""
    pass


class SendMessageError(TgBotError):
    """Raised when sending a message fails."""
    pass


@dataclass
class SendResult:
    """Result of a send message operation."""
    ok: bool
    message_id: int | None = None
    error: str | None = None
    retryable: bool = True
    wait_seconds: int | None = None


class TgBot(ProfileMixin):
    """Telegram bot client wrapper.

    Inherits profile operations from ProfileMixin:
    - change_profile
    - set_username
    - get_profile
    - profile_health_check
    - delete_all_profile_photos
    - upload_multiple_photos
    - get_joined_channels
    - get_profile_photos
    """

    def __init__(self, config: Config, anthropic_api_key: str | None = None):
        self.config = config
        self.anthropic_api_key = anthropic_api_key
        self._client: TelegramClient | None = None
        self._verification: ButtonVerification | None = None
        self._ai_verification: "AIVerificationAgent | None" = None

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

    @property
    def ai_verification(self) -> "AIVerificationAgent | None":
        """Get AI verification agent (lazy initialization)."""
        if not AI_VERIFICATION_AVAILABLE:
            return None

        if self._ai_verification is None and self.anthropic_api_key:
            self._ai_verification = AIVerificationAgent(
                self.client,
                api_key=self.anthropic_api_key,
            )

        return self._ai_verification

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
            # Check connection
            if self._client is None:
                result["error"] = "Client not initialized"
                return result

            if not self._client.is_connected():
                result["error"] = "Not connected to Telegram"
                return result
            result["connected"] = True

            # Check authorization
            if not await self._client.is_user_authorized():
                result["error"] = "Not authorized"
                return result
            result["authorized"] = True

            # Get user info
            me = await self._client.get_me()
            result["user_id"] = me.id
            result["username"] = me.username

            # Check for restrictions
            if me.restricted:
                result["restricted"] = True
                reason = me.restriction_reason if me.restriction_reason else "unknown"
                result["error"] = f"Account is restricted: {reason}"
                return result

            # All checks passed
            result["ok"] = True
            log.info(f"Health check passed for user {me.id}")

        except Exception as e:
            log.error(f"Health check failed: {e}")
            result["error"] = str(e)

        return result

    async def terminate_other_sessions(self) -> dict:
        """
        Terminate all other sessions except the current one.

        Returns:
            {
                "terminated": int - Number of sessions terminated
                "current_session_hash": int - Hash of the current session (kept)
            }
        """
        log.info("Terminating other sessions...")

        try:
            # Get all authorizations
            auths = await self.client(GetAuthorizationsRequest())

            terminated = 0
            current_hash = None

            for auth in auths.authorizations:
                if auth.current:
                    current_hash = auth.hash
                    log.debug(f"Keeping current session: {auth.app_name} ({auth.device_model})")
                    continue

                # Terminate this session
                log.debug(f"Terminating session: {auth.app_name} ({auth.device_model})")
                try:
                    await self.client(ResetAuthorizationRequest(hash=auth.hash))
                    terminated += 1
                except Exception as e:
                    log.warning(f"Failed to terminate session {auth.hash}: {e}")

            log.info(f"Terminated {terminated} other sessions")
            return {
                "terminated": terminated,
                "current_session_hash": current_hash,
            }

        except Exception as e:
            log.error(f"Failed to terminate sessions: {e}")
            raise TgBotError(f"Failed to terminate sessions: {e}")

    # ============ CHANNEL OPERATIONS ============

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
        log.info(f"Joining channel: {channel_link}")
        channel_id = None

        try:
            if "/+" in channel_link or "joinchat" in channel_link:
                invite_hash = channel_link.split("/")[-1].replace("+", "")
                log.debug(f"Using invite hash: {invite_hash}")
                await asyncio.sleep(random.uniform(1, 3))
                result = await self.client(ImportChatInviteRequest(invite_hash))
                channel_id = result.chats[0].id
                record_channel_join("success")
                log.info(f"Joined private channel: {channel_id}")
            else:
                username = channel_link.split("/")[-1]
                log.debug(f"Joining public channel: @{username}")
                entity = await self.client.get_entity(username)
                await asyncio.sleep(random.uniform(2, 5))
                await self.client(functions.channels.JoinChannelRequest(entity))
                channel_id = entity.id
                record_channel_join("success")
                log.info(f"Joined public channel: {channel_id}")

        except UserAlreadyParticipantError:
            log.info("Already a member, fetching channel ID")
            record_channel_join("already_member")
            await asyncio.sleep(random.uniform(1, 2))
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
                await asyncio.sleep(random.uniform(3, 7))
                await self.verification.verify(channel_id)
                if discussion_group_id:
                    await asyncio.sleep(random.uniform(2, 4))
                    await self.verification.verify(discussion_group_id)

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
                await asyncio.sleep(random.uniform(1, 3))
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
                    username = channel.split("/")[-1]
                    entity = await self.client.get_entity(username)
            else:
                # Direct ID
                entity = await self.client.get_entity(channel)

            channel_id = entity.id

            # Leave the channel/group
            await asyncio.sleep(random.uniform(1, 2))

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

    # ============ MESSAGE OPERATIONS ============

    def _handle_send_error(self, error: Exception, context: str = "Send") -> SendResult:
        """Handle common send/comment errors and return appropriate SendResult."""
        operation = context.lower()

        if isinstance(error, (ChatWriteForbiddenError, UserBannedInChannelError)):
            log.error(f"Banned or no write permission: {error}")
            record_message_sent("banned", operation)
            record_error("banned", operation)
            return SendResult(ok=False, error="banned", retryable=False)

        if isinstance(error, ChannelPrivateError):
            log.error(f"Channel is private or deleted: {error}")
            record_message_sent("channel_private", operation)
            record_error("channel_private", operation)
            return SendResult(ok=False, error="channel_private", retryable=False)

        if isinstance(error, ChatRestrictedError):
            log.error(f"Chat is restricted: {error}")
            record_message_sent("chat_restricted", operation)
            record_error("chat_restricted", operation)
            return SendResult(ok=False, error="chat_restricted", retryable=False)

        if isinstance(error, ForbiddenError):
            log.error(f"Forbidden: {error}")
            record_message_sent("forbidden", operation)
            record_error("forbidden", operation)
            return SendResult(ok=False, error="forbidden", retryable=False)

        if isinstance(error, FloodWaitError):
            log.warning(f"Rate limited for {error.seconds}s")
            record_message_sent("rate_limited", operation)
            record_rate_limit(operation, error.seconds)
            return SendResult(ok=False, error="flood_wait", retryable=True, wait_seconds=error.seconds)

        if isinstance(error, SlowModeWaitError):
            log.warning(f"Slow mode: wait {error.seconds}s")
            record_message_sent("slow_mode", operation)
            record_rate_limit(f"{operation}_slow_mode", error.seconds)
            return SendResult(ok=False, error="slow_mode", retryable=True, wait_seconds=error.seconds)

        log.error(f"{context} failed: {error}")
        record_message_sent("error", operation)
        record_error(type(error).__name__, operation)
        return SendResult(ok=False, error=str(error), retryable=True)

    async def send_message(
        self,
        target: int | str,
        text: str,
        reply_to: int | None = None,
        topic_id: int | None = None,
        check_verification: bool = False,
        verification_wait_seconds: float = 3.0,
    ) -> SendResult:
        """
        Send a message to a chat, channel, or user.
        Can also reply to a specific message or send to a forum topic.

        Args:
            target: Chat/channel/user ID or username
            text: Message text
            reply_to: Message ID to reply to
            topic_id: Forum topic ID (for supergroups with forum mode). If set, sends to this topic.
            check_verification: Check for verification after sending (for first message)
            verification_wait_seconds: How long to wait before checking

        Returns SendResult with:
            - ok: True if message was sent
            - message_id: ID of sent message (if ok)
            - error: Error message (if not ok)
            - retryable: False for permanent errors (banned, no permissions)
            - wait_seconds: Seconds to wait before retry (for rate limits)

        Note: For forum supergroups, you must specify topic_id to send to a specific topic.
              The General topic typically has ID=1.
        """
        log.info(f"Sending message to: {target}" + (f" (topic={topic_id})" if topic_id else ""))
        log.debug(f"Message text: {text[:50]}{'...' if len(text) > 50 else ''}")
        try:
            await asyncio.sleep(random.uniform(1, 3))

            # For forum topics, use reply_to with the topic ID
            # Telethon handles this by sending to the topic's thread
            if topic_id and not reply_to:
                # When sending to a topic without replying to a specific message,
                # use the topic_id as reply_to - Telethon routes it to the topic
                msg = await self.client.send_message(target, text, reply_to=topic_id)
            else:
                msg = await self.client.send_message(target, text, reply_to=reply_to)
            record_message_sent("success", "message")
            log.info(f"Message sent successfully (id={msg.id})")

            # Check for verification after first message
            if check_verification and self.ai_verification:
                log.info("Checking for post-message verification...")
                verification_result = await self.ai_verification.check_and_handle_verification(
                    chat_id=target,
                    our_message_id=msg.id,
                    context="after_message",
                    wait_seconds=verification_wait_seconds,
                )
                if verification_result.action_taken:
                    log.info(f"Verification handled: {verification_result.action_taken}")

            return SendResult(ok=True, message_id=msg.id)

        except Exception as e:
            return self._handle_send_error(e, "Send")

    async def send_comment(
        self,
        channel: int | str,
        post_id: int,
        text: str,
        reply_to: int | None = None,
        check_verification: bool = False,
        verification_wait_seconds: float = 3.0,
    ) -> SendResult:
        """
        Send a comment to a channel post (broadcast channels only).

        For supergroups and regular groups, use send_message() instead.

        Args:
            channel: Channel ID or username (must be a broadcast channel)
            post_id: Post ID to comment on
            text: Comment text
            reply_to: Message ID to reply to (for threading comments within discussion)
            check_verification: Check for verification after sending
            verification_wait_seconds: How long to wait before checking

        Returns SendResult (same as send_message).
        """
        log.info(f"Sending comment to post {post_id} in {channel}" + (f" (reply to {reply_to})" if reply_to else ""))
        try:
            # Verify target is a broadcast channel (comments only work on broadcast channels)
            target_type = await self.get_target_type(channel)
            if target_type != "channel":
                log.warning(f"Target {channel} is a {target_type}, not a broadcast channel. Comments only work on broadcast channels. Use send_message() for groups/supergroups.")
                return SendResult(
                    ok=False,
                    error=f"comments_not_supported: Target is a {target_type}, not a broadcast channel",
                    retryable=False
                )
            await asyncio.sleep(random.uniform(1, 3))

            # When reply_to is specified, we need to send directly to the discussion group
            # because Telethon's comment_to + reply_to combination doesn't properly
            # create reply chains within the comment thread
            if reply_to is not None:
                # Get the channel's linked discussion group
                channel_entity = await self.client.get_entity(channel)
                full_channel = await self.client(GetFullChannelRequest(channel_entity))

                if not full_channel.full_chat.linked_chat_id:
                    # No discussion group, fall back to standard comment
                    log.warning("Channel has no linked discussion group, using standard comment")
                    msg = await self.client.send_message(channel, text, comment_to=post_id)
                else:
                    # Send directly to discussion group with reply_to
                    # The reply_to here is the message ID in the discussion group
                    discussion_group_id = full_channel.full_chat.linked_chat_id
                    log.info(f"Sending to discussion group {discussion_group_id} with reply_to={reply_to}")
                    msg = await self.client.send_message(
                        discussion_group_id,
                        text,
                        reply_to=reply_to
                    )
            else:
                # First message in thread - use comment_to to start the thread
                msg = await self.client.send_message(channel, text, comment_to=post_id)

            record_message_sent("success", "comment")
            log.info(f"Comment sent successfully (id={msg.id})")

            # Check for verification after comment
            # Comments go to the discussion group, not the channel, so we need to check there
            if check_verification and self.ai_verification:
                log.info("Checking for post-comment verification...")

                # Get the channel entity and its linked discussion group
                channel_entity = await self.client.get_entity(channel)
                channel_id = channel_entity.id if hasattr(channel_entity, 'id') else channel

                # Use check_post_comments_verification which properly handles discussion groups
                # Pass our message ID so it can detect replies to our comment
                verification_result = await self.ai_verification.check_post_comments_verification(
                    channel_id=channel_id,
                    discussion_group_id=None,  # Will be auto-detected
                    our_message_id=msg.id,  # The comment message ID (in discussion group)
                    wait_seconds=verification_wait_seconds,
                )
                if verification_result.action_taken:
                    log.info(f"Verification handled: {verification_result.action_taken}")
                elif verification_result.error:
                    log.warning(f"Verification check failed: {verification_result.error}")

            return SendResult(ok=True, message_id=msg.id)

        except Exception as e:
            return self._handle_send_error(e, "Comment")

    async def verify_in_comments(self, channel: int | str, post_id: int) -> bool:
        """
        Check for and handle verification bot messages in post comments.
        Call this after sending a comment to handle bots like Combot.

        Returns True if verification was handled (or not needed).
        """
        log.info(f"Checking for verification bots in comments of post {post_id}")
        try:
            await asyncio.sleep(random.uniform(2, 4))

            # Get recent comments on this post
            entity = await self.client.get_entity(channel)

            # Get the discussion/comments for this post
            async for message in self.client.iter_messages(
                entity,
                reply_to=post_id,
                limit=10
            ):
                sender = await message.get_sender()
                if not sender:
                    continue

                # Check if sender is a bot
                is_bot = hasattr(sender, "bot") and sender.bot
                if not is_bot:
                    continue

                bot_name = getattr(sender, 'first_name', 'Unknown')
                bot_username = getattr(sender, 'username', 'unknown')
                log.info(f"Found bot in comments: {bot_name} (@{bot_username})")

                # Check for buttons
                if message.reply_markup and hasattr(message.reply_markup, "rows"):
                    rows = message.reply_markup.rows
                    for row in rows:
                        for button in row.buttons:
                            button_type = type(button).__name__

                            if button_type == "KeyboardButtonCallback":
                                log.info(f"Clicking verification button: {button.text}")
                                await asyncio.sleep(random.uniform(2, 5))
                                try:
                                    result = await message.click(data=button.data)
                                    result_msg = result.message if result else "OK"
                                    log.info(f"Verification button clicked: {result_msg}")
                                    await asyncio.sleep(random.uniform(2, 4))
                                    return True
                                except FloodWaitError as e:
                                    log.warning(f"Rate limited clicking button: {e.seconds}s")
                                    await asyncio.sleep(e.seconds + 5)
                                    return False
                                except Exception as e:
                                    log.warning(f"Button click failed: {e}")
                                    continue

            log.info("No verification bot found in comments")
            return True

        except Exception as e:
            log.error(f"Error checking verification in comments: {e}")
            return False

    async def get_target_type(self, target: int | str) -> str:
        """
        Determine if a target is a channel, supergroup, or group.

        Returns:
            "channel" for broadcast channels (can only comment on posts)
            "supergroup" for supergroups (can send direct messages)
            "group" for basic groups (can send direct messages)
        """
        try:
            entity = await self.client.get_entity(target)

            if isinstance(entity, Channel):
                if entity.broadcast:
                    return "channel"
                else:
                    return "supergroup"
            elif isinstance(entity, Chat):
                return "group"
            else:
                return "unknown"

        except Exception as e:
            log.error(f"Failed to get target type: {e}")
            raise TgBotError(f"Failed to get target type: {e}")

    async def check_channel_membership(self, target: int | str) -> dict:
        """
        Check if the account is a member of a channel/group and get its type.

        This method handles private channels with invite links correctly by
        refreshing the dialogs cache if the initial lookup fails.

        Args:
            target: Channel username, ID, or invite link (t.me/+xxx)

        Returns:
            dict with:
                - is_member: bool
                - target_type: "channel" | "supergroup" | "group" | None
                - channel_id: int | None (the resolved channel ID)
                - error: str | None (error message if not a member)
        """
        result = {
            "is_member": False,
            "target_type": None,
            "channel_id": None,
            "error": None,
        }

        # First try direct entity lookup (works for public channels and cached entities)
        try:
            entity = await self.client.get_entity(target)

            if isinstance(entity, Channel):
                result["is_member"] = True
                result["channel_id"] = entity.id
                result["target_type"] = "channel" if entity.broadcast else "supergroup"
            elif isinstance(entity, Chat):
                result["is_member"] = True
                result["channel_id"] = entity.id
                result["target_type"] = "group"
            else:
                result["is_member"] = True
                result["channel_id"] = getattr(entity, 'id', None)
                result["target_type"] = "unknown"

            return result

        except Exception as e:
            error_msg = str(e).lower()
            if "not part of" not in error_msg and "cannot get entity" not in error_msg:
                # Some other error - not a membership issue
                result["error"] = str(e)
                return result

        # Direct lookup failed - refresh dialogs and try to find the channel
        log.info(f"Direct lookup failed for {target}, refreshing dialogs cache...")

        try:
            # Refresh dialogs to populate session cache
            async for dialog in self.client.iter_dialogs():
                entity = dialog.entity

                # Check if this is the target we're looking for
                if isinstance(entity, (Channel, Chat)):
                    # Match by ID if target is numeric
                    if isinstance(target, int) and entity.id == target:
                        result["is_member"] = True
                        result["channel_id"] = entity.id
                        if isinstance(entity, Channel):
                            result["target_type"] = "channel" if entity.broadcast else "supergroup"
                        else:
                            result["target_type"] = "group"
                        return result

                    # Match by username
                    if isinstance(target, str):
                        username = getattr(entity, 'username', None)
                        if username and target.lower().lstrip('@') == username.lower():
                            result["is_member"] = True
                            result["channel_id"] = entity.id
                            if isinstance(entity, Channel):
                                result["target_type"] = "channel" if entity.broadcast else "supergroup"
                            else:
                                result["target_type"] = "group"
                            return result

            # After refreshing dialogs, try get_entity again
            # (the entity should now be in the session cache)
            try:
                entity = await self.client.get_entity(target)

                if isinstance(entity, Channel):
                    result["is_member"] = True
                    result["channel_id"] = entity.id
                    result["target_type"] = "channel" if entity.broadcast else "supergroup"
                elif isinstance(entity, Chat):
                    result["is_member"] = True
                    result["channel_id"] = entity.id
                    result["target_type"] = "group"
                else:
                    result["is_member"] = True
                    result["channel_id"] = getattr(entity, 'id', None)
                    result["target_type"] = "unknown"

                return result

            except Exception as e2:
                log.warning(f"Still cannot resolve {target} after dialog refresh: {e2}")
                result["error"] = f"Not a member of target channel (checked via dialogs)"
                return result

        except Exception as e:
            log.error(f"Error refreshing dialogs: {e}")
            result["error"] = f"Cannot verify membership: {e}"
            return result

    async def get_latest_post(self, channel: int | str, with_comments: bool = True) -> dict | None:
        """
        Get the latest post from a broadcast channel.

        Args:
            channel: Channel username or ID
            with_comments: If True, only return posts that have comments enabled

        Returns:
            Dict with post info: {id, text, date, views, comments_enabled}
            or None if no suitable post found
        """
        log.info(f"Getting latest post from: {channel}")
        try:
            entity = await self.client.get_entity(channel)

            # Get recent messages from the channel
            async for message in self.client.iter_messages(entity, limit=10):
                # Skip service messages (joins, pins, etc.)
                if message.action is not None:
                    continue

                # Check if comments are enabled on this post
                comments_enabled = hasattr(message, 'replies') and message.replies is not None

                if with_comments and not comments_enabled:
                    continue

                return {
                    "id": message.id,
                    "text": message.text or "",
                    "date": message.date.isoformat() if message.date else None,
                    "views": getattr(message, 'views', None),
                    "comments_enabled": comments_enabled,
                }

            log.warning(f"No suitable post found in {channel}")
            return None

        except Exception as e:
            log.error(f"Failed to get latest post: {e}")
            raise TgBotError(f"Failed to get latest post: {e}")

    async def send_reaction(
        self,
        channel: int | str,
        message_id: int,
        emoji: str = "👍",
    ) -> SendResult:
        """
        Send a reaction to a channel post.

        Args:
            channel: Channel ID or username
            message_id: Post ID to react to
            emoji: Emoji to react with (default: 👍)

        Returns:
            SendResult with ok=True if successful
        """
        log.info(f"Sending reaction {emoji} to message {message_id} in {channel}")
        try:
            await asyncio.sleep(random.uniform(1, 3))
            entity = await self.client.get_entity(channel)

            # Send the reaction
            await self.client(SendReactionRequest(
                peer=entity,
                msg_id=message_id,
                reaction=[ReactionEmoji(emoticon=emoji)],
            ))

            log.info(f"Reaction {emoji} sent successfully to message {message_id}")
            return SendResult(ok=True, message_id=message_id)

        except FloodWaitError as e:
            log.warning(f"Rate limited for {e.seconds}s while sending reaction")
            return SendResult(ok=False, error="flood_wait", retryable=True, wait_seconds=e.seconds)

        except Exception as e:
            log.error(f"Failed to send reaction: {e}")
            return SendResult(ok=False, error=str(e), retryable=True)

    async def get_recent_posts(
        self,
        channel: int | str,
        limit: int = 10,
    ) -> list[dict]:
        """
        Get recent posts from a channel for warmup activities.

        Args:
            channel: Channel ID or username
            limit: Number of posts to fetch

        Returns:
            List of dicts with post info: [{id, text, date, views}, ...]
        """
        log.info(f"Getting {limit} recent posts from: {channel}")
        try:
            entity = await self.client.get_entity(channel)
            posts = []

            async for message in self.client.iter_messages(entity, limit=limit):
                # Skip service messages
                if message.action is not None:
                    continue

                posts.append({
                    "id": message.id,
                    "text": (message.text or "")[:200],
                    "date": message.date.isoformat() if message.date else None,
                    "views": getattr(message, 'views', None),
                })

            log.info(f"Found {len(posts)} posts in {channel}")
            return posts

        except Exception as e:
            log.error(f"Failed to get recent posts: {e}")
            raise TgBotError(f"Failed to get recent posts: {e}")

    async def get_forum_topics(
        self,
        channel: int | str,
        limit: int = 100,
    ) -> list[dict]:
        """
        Get forum topics from a supergroup with forum mode enabled.

        Args:
            channel: Supergroup ID or username
            limit: Maximum number of topics to fetch

        Returns:
            List of dicts with topic info:
            [
                {
                    "id": int,  # Topic ID (use as topic_id in send_message)
                    "title": str,
                    "icon_emoji_id": int | None,
                    "is_general": bool,  # True for the General topic
                    "is_closed": bool,
                    "is_hidden": bool,
                }
            ]

        Raises:
            TgBotError: If the target is not a forum supergroup
        """
        from telethon.tl.functions.channels import GetForumTopicsRequest

        log.info(f"Getting forum topics from: {channel}")
        try:
            entity = await self.client.get_entity(channel)

            # Verify it's a forum supergroup
            if not isinstance(entity, Channel) or entity.broadcast:
                raise TgBotError(f"Target {channel} is not a supergroup")
            if not getattr(entity, 'forum', False):
                raise TgBotError(f"Supergroup {channel} does not have forum mode enabled")

            # Get forum topics
            result = await self.client(GetForumTopicsRequest(
                channel=entity,
                offset_date=0,
                offset_id=0,
                offset_topic=0,
                limit=limit,
            ))

            topics = []
            for topic in result.topics:
                topics.append({
                    "id": topic.id,
                    "title": topic.title,
                    "icon_emoji_id": getattr(topic, 'icon_emoji_id', None),
                    "is_general": getattr(topic, 'short', False),  # General topic has 'short' flag
                    "is_closed": getattr(topic, 'closed', False),
                    "is_hidden": getattr(topic, 'hidden', False),
                })

            log.info(f"Found {len(topics)} forum topics in {channel}")
            return topics

        except TgBotError:
            raise
        except Exception as e:
            log.error(f"Failed to get forum topics: {e}")
            raise TgBotError(f"Failed to get forum topics: {e}")

    async def get_recent_messages_in_topic(
        self,
        channel: int | str,
        topic_id: int,
        limit: int = 10,
    ) -> list[dict]:
        """
        Get recent messages from a specific forum topic.

        Args:
            channel: Supergroup ID or username
            topic_id: Forum topic ID
            limit: Number of messages to fetch

        Returns:
            List of dicts with message info: [{id, text, date, sender_id, sender_username}, ...]
        """
        log.info(f"Getting {limit} recent messages from topic {topic_id} in {channel}")
        try:
            entity = await self.client.get_entity(channel)
            messages = []

            # Use reply_to parameter to filter messages in a specific topic
            async for message in self.client.iter_messages(entity, limit=limit, reply_to=topic_id):
                # Skip service messages
                if message.action is not None:
                    continue

                sender = await message.get_sender() if message.sender_id else None
                messages.append({
                    "id": message.id,
                    "text": (message.text or "")[:200],
                    "date": message.date.isoformat() if message.date else None,
                    "sender_id": message.sender_id,
                    "sender_username": getattr(sender, 'username', None) if sender else None,
                })

            log.info(f"Found {len(messages)} messages in topic {topic_id}")
            return messages

        except Exception as e:
            log.error(f"Failed to get messages from topic: {e}")
            raise TgBotError(f"Failed to get messages from topic: {e}")

    # ============ CHANNEL INFO ============

    async def get_channel_info(
        self,
        channel: int | str,
        posts_limit: int = 10,
        text_length: int = 500,
    ) -> dict:
        """
        Get detailed information about a channel or group.

        Args:
            channel: Channel ID, username, or invite link
            posts_limit: Maximum number of recent posts to fetch (default 10)
            text_length: Maximum text length per post (default 500)

        Returns:
            {
                "id": int,
                "title": str,
                "username": str | None,
                "description": str | None,
                "member_count": int | None,
                "type": "channel" | "supergroup" | "group",
                "is_verified": bool,
                "is_scam": bool,
                "is_fake": bool,
                "recent_posts": [  # Only for broadcast channels
                    {
                        "id": int,
                        "text": str,
                        "date": str,
                        "views": int | None,
                    }
                ]
            }
        """
        log.info(f"Fetching channel info for: {channel} (posts_limit={posts_limit}, text_length={text_length})")

        try:
            # Get the entity
            entity = await self.client.get_entity(channel)

            result = {
                "id": entity.id,
                "title": getattr(entity, 'title', None),
                "username": getattr(entity, 'username', None),
                "description": None,
                "member_count": None,
                "type": "group",
                "is_verified": False,
                "is_scam": False,
                "is_fake": False,
                "recent_posts": [],
            }

            if isinstance(entity, Channel):
                result["type"] = "channel" if entity.broadcast else "supergroup"
                result["is_verified"] = getattr(entity, 'verified', False)
                result["is_scam"] = getattr(entity, 'scam', False)
                result["is_fake"] = getattr(entity, 'fake', False)
                # Check if supergroup has forum mode enabled (topics)
                result["is_forum"] = getattr(entity, 'forum', False) if not entity.broadcast else False

                # Get full channel info for description and member count
                try:
                    full_channel = await self.client(GetFullChannelRequest(entity))
                    result["description"] = getattr(full_channel.full_chat, 'about', None)
                    result["member_count"] = getattr(full_channel.full_chat, 'participants_count', None)
                    # Check if channel has linked discussion group (comments enabled)
                    linked_chat_id = getattr(full_channel.full_chat, 'linked_chat_id', None)
                    result["comments_enabled"] = linked_chat_id is not None
                    result["discussion_group_id"] = linked_chat_id
                except Exception as e:
                    log.warning(f"Could not get full channel info: {e}")
                    result["member_count"] = getattr(entity, 'participants_count', None)
                    result["comments_enabled"] = None  # Unknown
                    result["discussion_group_id"] = None

                # Get recent posts for broadcast channels
                if entity.broadcast:
                    try:
                        posts = []
                        async for message in self.client.iter_messages(entity, limit=posts_limit):
                            # Skip service messages
                            if message.action is not None:
                                continue
                            posts.append({
                                "id": message.id,
                                "text": (message.text or "")[:text_length],  # Truncate long texts
                                "date": message.date.isoformat() if message.date else None,
                                "views": getattr(message, 'views', None),
                            })
                        result["recent_posts"] = posts
                    except Exception as e:
                        log.warning(f"Could not fetch recent posts: {e}")

            elif isinstance(entity, Chat):
                result["type"] = "group"
                result["member_count"] = getattr(entity, 'participants_count', None)

            log.info(f"Got channel info: {result['title']} ({result['type']}, {result['member_count']} members)")
            return result

        except Exception as e:
            log.error(f"Failed to get channel info: {e}")
            raise TgBotError(f"Failed to get channel info: {e}")
