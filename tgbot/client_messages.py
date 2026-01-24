"""
Message operations mixin for TgBot.

This module provides message-related operations:
- send_message
- send_comment
- verify_in_comments
- send_reaction
"""
import asyncio
from dataclasses import dataclass
from telethon.errors import (
    FloodWaitError,
    ChatWriteForbiddenError,
    UserBannedInChannelError,
    ChannelPrivateError,
    ChatRestrictedError,
    SlowModeWaitError,
    ForbiddenError,
)
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.types import ReactionEmoji

from .utils.logger import setup_logger
from .utils.metrics import (
    record_message_sent,
    record_rate_limit,
    record_error,
)
from .utils.constants import (
    WAIT_NORMAL,
    WAIT_MEDIUM,
    WAIT_MEDIUM_LONG,
    DELAY_RATE_LIMIT_BASE,
    random_wait,
)

log = setup_logger("tg-bot.messages")


@dataclass
class SendResult:
    """Result of a send message operation."""
    ok: bool
    message_id: int | None = None
    error: str | None = None
    retryable: bool = True
    wait_seconds: int | None = None


class MessagesMixin:
    """Mixin providing message operations for TgBot."""

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
            await asyncio.sleep(random_wait(WAIT_NORMAL))

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
            await asyncio.sleep(random_wait(WAIT_NORMAL))

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
            await asyncio.sleep(random_wait(WAIT_MEDIUM))

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
                                await asyncio.sleep(random_wait(WAIT_MEDIUM_LONG))
                                try:
                                    result = await message.click(data=button.data)
                                    result_msg = result.message if result else "OK"
                                    log.info(f"Verification button clicked: {result_msg}")
                                    await asyncio.sleep(random_wait(WAIT_MEDIUM))
                                    return True
                                except FloodWaitError as e:
                                    log.warning(f"Rate limited clicking button: {e.seconds}s")
                                    await asyncio.sleep(e.seconds + DELAY_RATE_LIMIT_BASE)
                                    return False
                                except Exception as e:
                                    log.warning(f"Button click failed: {e}")
                                    continue

            log.info("No verification bot found in comments")
            return True

        except Exception as e:
            log.error(f"Error checking verification in comments: {e}")
            return False

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
            await asyncio.sleep(random_wait(WAIT_NORMAL))
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
