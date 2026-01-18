"""Listener that monitors Telegram groups and publishes messages to Redis."""

import asyncio
import logging
import signal
import uuid
from datetime import datetime
from typing import Callable

from telethon import events
from telethon.tl.types import Message

from ..client import TgBot
from ..utils.config import Config
from .redis_stream import ChannelMessage, MessageStream, HeartbeatManager

logger = logging.getLogger(__name__)


class Listener:
    """
    Listens to Telegram messages and publishes them to Redis stream.

    Uses the existing TgBot infrastructure for connection management.
    """

    def __init__(
        self,
        config: Config,
        message_stream: MessageStream,
        heartbeat_manager: HeartbeatManager,
        listener_id: str | None = None,
        account_id: int | None = None,
        heartbeat_interval: int = 10,
        on_message: Callable[[ChannelMessage], None] | None = None,
    ):
        self.config = config
        self.message_stream = message_stream
        self.heartbeat_manager = heartbeat_manager
        self.listener_id = listener_id or f"listener-{uuid.uuid4().hex[:8]}"
        self.account_id = account_id or 0
        self.heartbeat_interval = heartbeat_interval
        self.on_message = on_message  # Optional callback for debug

        self._bot: TgBot | None = None
        self._running = False
        self._assigned_groups: set[int] = set()
        self._messages_received = 0
        self._heartbeat_task: asyncio.Task | None = None
        self._shutdown_event = asyncio.Event()
        self._last_error: str | None = None

    @property
    def bot(self) -> TgBot:
        if self._bot is None:
            raise RuntimeError("Bot not initialized. Call start() first.")
        return self._bot

    @property
    def profile_name(self) -> str:
        """Get profile name from config path."""
        return self.config.session_path.name

    async def start(self) -> bool:
        """Start the listener - connect to Telegram."""
        logger.info(f"[{self.listener_id}] Starting listener for profile: {self.profile_name}")

        try:
            self._bot = TgBot(self.config)
            await self._bot.connect()

            # Register message handler
            self._register_handler()

            logger.info(f"[{self.listener_id}] Connected successfully")
            return True

        except Exception as e:
            self._last_error = str(e)
            logger.error(f"[{self.listener_id}] Failed to start: {e}")
            return False

    async def stop(self):
        """Stop the listener gracefully."""
        logger.info(f"[{self.listener_id}] Stopping listener...")
        self._running = False
        self._shutdown_event.set()

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        if self._bot:
            await self._bot.disconnect()
            self._bot = None

        self.heartbeat_manager.remove_heartbeat(self.listener_id)
        logger.info(f"[{self.listener_id}] Stopped")

    def assign_groups(self, group_ids: list[int]):
        """
        Assign specific groups to listen to.

        If empty, listens to all groups the account is part of.
        Telethon accepts raw IDs - it handles the -100 prefix conversion internally.
        """
        self._assigned_groups = set(group_ids)
        logger.info(f"[{self.listener_id}] Assigned {len(group_ids)} groups: {list(group_ids)}")

        # Re-register handler with new filter if already running
        if self._bot and self._bot._client and self._bot._client.is_connected():
            self._register_handler()

    def _register_handler(self):
        """Register the message event handler."""
        print(f"[{self.listener_id}] Registering message handler...")
        client = self._bot.client

        # Remove existing handler if any
        try:
            client.remove_event_handler(self._on_new_message)
        except ValueError:
            pass  # Handler wasn't registered

        # Add handler - we filter in _on_new_message instead for better debugging
        client.add_event_handler(
            self._on_new_message,
            events.NewMessage()
        )
        print(f"[{self.listener_id}] Handler registered for all messages, filtering groups: {self._assigned_groups}")

    async def _on_new_message(self, event: events.NewMessage.Event):
        """Handle incoming messages."""
        try:
            message: Message = event.message
            chat_id = event.chat_id

            # Log all incoming messages for debugging
            print(f"[{self.listener_id}] >>> Received message from chat_id={chat_id}")

            # Temporarily disabled filtering for debugging - capture ALL messages
            # TODO: Re-enable filtering once basic functionality confirmed
            print(f"[{self.listener_id}] Processing message from chat_id={chat_id} (filtering disabled for debug)")

            # Skip messages without text
            if not message.text:
                return

            # Get sender info
            sender = await event.get_sender()
            sender_id = sender.id if sender else None
            sender_username = getattr(sender, 'username', None)

            # Check if this is a reply
            reply_to_msg_id = None
            if message.reply_to:
                reply_to_msg_id = message.reply_to.reply_to_msg_id

            # Get chat/group info
            chat_id = event.chat_id

            # Create message object
            channel_msg = ChannelMessage(
                channel_id=chat_id,
                message_id=message.id,
                text=message.text[:2000],  # Truncate very long messages
                sender_id=sender_id,
                sender_username=sender_username,
                message_date=message.date.isoformat() if message.date else datetime.utcnow().isoformat(),
                has_media=message.media is not None,
                media_type=type(message.media).__name__ if message.media else None,
                reply_to_msg_id=reply_to_msg_id,
                discussion_group_id=chat_id,
                listener_id=self.listener_id,
            )

            # Publish to Redis stream
            self.message_stream.publish(channel_msg)
            self._messages_received += 1

            # Call optional callback (for debug UI)
            if self.on_message:
                self.on_message(channel_msg)

            logger.debug(
                f"[{self.listener_id}] Message from {chat_id} by @{sender_username}: "
                f"{message.text[:50]}{'...' if len(message.text) > 50 else ''}"
            )

        except Exception as e:
            logger.error(f"[{self.listener_id}] Error processing message: {e}")
            self._last_error = str(e)

    async def _heartbeat_loop(self):
        """Send periodic heartbeats."""
        while self._running:
            try:
                self.heartbeat_manager.send_heartbeat(
                    listener_id=self.listener_id,
                    account_id=self.account_id,
                    profile_name=self.profile_name,
                    channel_count=len(self._assigned_groups),
                    messages_received=self._messages_received,
                    status="listening",
                    error=self._last_error,
                )
                # Clear last error after successful heartbeat
                self._last_error = None
            except Exception as e:
                logger.error(f"[{self.listener_id}] Heartbeat error: {e}")

            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=self.heartbeat_interval
                )
                # Shutdown event was set
                break
            except asyncio.TimeoutError:
                # Normal timeout, continue heartbeat loop
                pass

    async def run(self):
        """Run the listener (blocking until stopped)."""
        if not self._bot:
            if not await self.start():
                return

        self._running = True
        self._shutdown_event.clear()

        # Start heartbeat task
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        logger.info(
            f"[{self.listener_id}] Listening "
            f"({'all groups' if not self._assigned_groups else f'{len(self._assigned_groups)} groups'})..."
        )

        try:
            # Keep running until disconnected
            await self._bot.client.run_until_disconnected()
        except asyncio.CancelledError:
            logger.info(f"[{self.listener_id}] Listener cancelled")
        finally:
            await self.stop()

    async def run_with_signal_handling(self):
        """Run with SIGINT/SIGTERM handling for graceful shutdown."""
        loop = asyncio.get_event_loop()

        def signal_handler():
            logger.info(f"[{self.listener_id}] Received shutdown signal")
            self._shutdown_event.set()
            if self._bot and self._bot._client:
                self._bot._client.disconnect()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, signal_handler)
            except NotImplementedError:
                # Windows doesn't support add_signal_handler
                pass

        await self.run()

    @property
    def stats(self) -> dict:
        """Get current listener stats."""
        return {
            "listener_id": self.listener_id,
            "profile_name": self.profile_name,
            "account_id": self.account_id,
            "running": self._running,
            "groups_count": len(self._assigned_groups),
            "messages_received": self._messages_received,
            "last_error": self._last_error,
        }
