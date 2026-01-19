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
    UsernameOccupiedError,
    UsernameInvalidError,
    UsernameNotModifiedError,
)
from telethon.tl.functions.account import UpdateProfileRequest, UpdateUsernameRequest, GetAuthorizationsRequest, ResetAuthorizationRequest
from telethon.tl.functions.messages import ImportChatInviteRequest, CheckChatInviteRequest, GetDialogsRequest
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.messages import SendReactionRequest, GetMessagesViewsRequest
from telethon.tl.types import ReactionEmoji
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.photos import GetUserPhotosRequest, DeletePhotosRequest
from telethon.tl.types import Channel, Chat, InputPeerEmpty

from .utils.config import Config
from .utils.logger import setup_logger
from .utils.metrics import (
    record_channel_join,
    record_message_sent,
    record_rate_limit,
    record_error,
    record_profile_update,
    record_verification,
)
from .verification import ButtonVerification

# Import AI verification (optional - may not be available if anthropic not installed)
try:
    from .verification import AIVerificationAgent, VerificationResult
    AI_VERIFICATION_AVAILABLE = True
except ImportError:
    AI_VERIFICATION_AVAILABLE = False
    AIVerificationAgent = None
    VerificationResult = None

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

    async def terminate_other_sessions(self) -> dict:
        """
        Terminate all other active Telegram sessions except the current one.

        This is a security measure to ensure only our bot session is active.

        Returns:
            dict with:
                - terminated: int - Number of sessions terminated
                - kept: int - Number of sessions kept (current session)
                - sessions: list - Details of terminated sessions
                - error: str | None - Error message if any
        """
        result = {
            "terminated": 0,
            "kept": 0,
            "sessions": [],
            "error": None,
        }

        try:
            # Get all active authorizations
            authorizations = await self.client(GetAuthorizationsRequest())

            for auth in authorizations.authorizations:
                if auth.current:
                    # This is our current session, keep it
                    result["kept"] += 1
                    log.debug(f"Keeping current session: {auth.device_model} ({auth.platform})")
                else:
                    # Terminate this session
                    try:
                        await self.client(ResetAuthorizationRequest(hash=auth.hash))
                        result["terminated"] += 1
                        result["sessions"].append({
                            "device": auth.device_model,
                            "platform": auth.platform,
                            "app": auth.app_name,
                            "location": f"{auth.country}, {auth.region}",
                            "date_created": str(auth.date_created) if auth.date_created else None,
                            "date_active": str(auth.date_active) if auth.date_active else None,
                        })
                        log.info(f"Terminated session: {auth.device_model} ({auth.platform}) - {auth.app_name}")
                    except Exception as e:
                        log.warning(f"Failed to terminate session {auth.hash}: {e}")

            log.info(f"Session cleanup complete: {result['terminated']} terminated, {result['kept']} kept")

        except Exception as e:
            result["error"] = str(e)
            log.error(f"Failed to get/terminate sessions: {e}")

        return result

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
            record_rate_limit("profile_update", e.seconds)
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
