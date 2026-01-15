"""Tests for tgbot.client module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from telethon.errors import (
    FloodWaitError,
    ChatWriteForbiddenError,
    UserBannedInChannelError,
    ChannelPrivateError,
    SlowModeWaitError,
)

from tgbot.client import (
    TgBot,
    TgBotError,
    JoinChannelError,
    SendMessageError,
    ProfileUpdateError,
    SendResult,
)


class TestSendResult:
    """Tests for SendResult dataclass."""

    def test_default_values(self):
        """Test SendResult default values."""
        result = SendResult(ok=True)
        assert result.ok is True
        assert result.message_id is None
        assert result.error is None
        assert result.retryable is True
        assert result.wait_seconds is None

    def test_success_result(self):
        """Test successful send result."""
        result = SendResult(ok=True, message_id=123)
        assert result.ok is True
        assert result.message_id == 123
        assert result.error is None

    def test_error_result(self):
        """Test error send result."""
        result = SendResult(
            ok=False,
            error="banned",
            retryable=False,
        )
        assert result.ok is False
        assert result.error == "banned"
        assert result.retryable is False

    def test_rate_limited_result(self):
        """Test rate limited result with wait time."""
        result = SendResult(
            ok=False,
            error="flood_wait",
            retryable=True,
            wait_seconds=60,
        )
        assert result.ok is False
        assert result.error == "flood_wait"
        assert result.retryable is True
        assert result.wait_seconds == 60


class TestExceptions:
    """Tests for custom exception classes."""

    def test_tgbot_error(self):
        """Test TgBotError exception."""
        error = TgBotError("Test error")
        assert str(error) == "Test error"
        assert isinstance(error, Exception)

    def test_join_channel_error(self):
        """Test JoinChannelError inherits from TgBotError."""
        error = JoinChannelError("Join failed")
        assert str(error) == "Join failed"
        assert isinstance(error, TgBotError)
        assert isinstance(error, Exception)

    def test_send_message_error(self):
        """Test SendMessageError inherits from TgBotError."""
        error = SendMessageError("Send failed")
        assert str(error) == "Send failed"
        assert isinstance(error, TgBotError)

    def test_profile_update_error(self):
        """Test ProfileUpdateError inherits from TgBotError."""
        error = ProfileUpdateError("Update failed")
        assert str(error) == "Update failed"
        assert isinstance(error, TgBotError)


class TestTgBotInit:
    """Tests for TgBot initialization."""

    def test_init_without_anthropic_key(self, mock_config):
        """Test initialization without anthropic API key."""
        bot = TgBot(mock_config)
        assert bot.config == mock_config
        assert bot.anthropic_api_key is None
        assert bot._client is None
        assert bot._verification is None

    def test_init_with_anthropic_key(self, mock_config):
        """Test initialization with anthropic API key."""
        bot = TgBot(mock_config, anthropic_api_key="test_key")
        assert bot.anthropic_api_key == "test_key"

    def test_client_property_raises_before_connect(self, mock_config):
        """Test that accessing client before connect raises error."""
        bot = TgBot(mock_config)
        with pytest.raises(TgBotError, match="Client not initialized"):
            _ = bot.client


class TestTgBotHealthCheck:
    """Tests for TgBot.health_check() method."""

    async def test_health_check_success(self, mock_config, mock_telegram_client):
        """Test successful health check."""
        bot = TgBot(mock_config)
        bot._client = mock_telegram_client

        result = await bot.health_check()

        assert result["ok"] is True
        assert result["connected"] is True
        assert result["authorized"] is True
        assert result["user_id"] == 12345
        assert result["username"] == "testuser"
        assert result["restricted"] is False
        assert result["error"] is None

    async def test_health_check_not_initialized(self, mock_config):
        """Test health check when client not initialized."""
        bot = TgBot(mock_config)
        result = await bot.health_check()

        assert result["ok"] is False
        assert result["error"] == "Client not initialized"

    async def test_health_check_not_connected(self, mock_config, mock_telegram_client):
        """Test health check when not connected."""
        mock_telegram_client.is_connected = MagicMock(return_value=False)
        bot = TgBot(mock_config)
        bot._client = mock_telegram_client

        result = await bot.health_check()

        assert result["ok"] is False
        assert result["connected"] is False
        assert result["error"] == "Client not connected"

    async def test_health_check_not_authorized(self, mock_config, mock_telegram_client):
        """Test health check when not authorized."""
        mock_telegram_client.is_user_authorized = AsyncMock(return_value=False)
        bot = TgBot(mock_config)
        bot._client = mock_telegram_client

        result = await bot.health_check()

        assert result["ok"] is False
        assert result["authorized"] is False
        assert result["error"] == "User not authorized"

    async def test_health_check_restricted_account(self, mock_config, mock_telegram_client):
        """Test health check with restricted account."""
        mock_user = mock_telegram_client.get_me.return_value
        mock_user.restricted = True
        mock_user.restriction_reason = "spam"

        bot = TgBot(mock_config)
        bot._client = mock_telegram_client

        result = await bot.health_check()

        assert result["ok"] is False
        assert result["restricted"] is True
        assert result["error"] == "Account is restricted"


class TestTgBotSendMessage:
    """Tests for TgBot.send_message() method."""

    async def test_send_message_success(self, mock_config, mock_telegram_client):
        """Test successful message send."""
        mock_msg = MagicMock()
        mock_msg.id = 999
        mock_telegram_client.send_message = AsyncMock(return_value=mock_msg)

        bot = TgBot(mock_config)
        bot._client = mock_telegram_client

        with patch("tgbot.client.asyncio.sleep", new_callable=AsyncMock):
            result = await bot.send_message("testchat", "Hello world")

        assert result.ok is True
        assert result.message_id == 999
        mock_telegram_client.send_message.assert_called_once()

    async def test_send_message_with_reply(self, mock_config, mock_telegram_client):
        """Test message send with reply_to."""
        mock_msg = MagicMock()
        mock_msg.id = 1000
        mock_telegram_client.send_message = AsyncMock(return_value=mock_msg)

        bot = TgBot(mock_config)
        bot._client = mock_telegram_client

        with patch("tgbot.client.asyncio.sleep", new_callable=AsyncMock):
            result = await bot.send_message("testchat", "Reply text", reply_to=500)

        assert result.ok is True
        mock_telegram_client.send_message.assert_called_once_with(
            "testchat", "Reply text", reply_to=500
        )

    async def test_send_message_banned(self, mock_config, mock_telegram_client):
        """Test send when user is banned."""
        mock_telegram_client.send_message = AsyncMock(
            side_effect=ChatWriteForbiddenError(request=None)
        )

        bot = TgBot(mock_config)
        bot._client = mock_telegram_client

        with patch("tgbot.client.asyncio.sleep", new_callable=AsyncMock):
            result = await bot.send_message("testchat", "Hello")

        assert result.ok is False
        assert result.error == "banned"
        assert result.retryable is False

    async def test_send_message_user_banned_in_channel(self, mock_config, mock_telegram_client):
        """Test send when user is banned in channel."""
        mock_telegram_client.send_message = AsyncMock(
            side_effect=UserBannedInChannelError(request=None)
        )

        bot = TgBot(mock_config)
        bot._client = mock_telegram_client

        with patch("tgbot.client.asyncio.sleep", new_callable=AsyncMock):
            result = await bot.send_message("testchat", "Hello")

        assert result.ok is False
        assert result.error == "banned"
        assert result.retryable is False

    async def test_send_message_channel_private(self, mock_config, mock_telegram_client):
        """Test send to private/deleted channel."""
        mock_telegram_client.send_message = AsyncMock(
            side_effect=ChannelPrivateError(request=None)
        )

        bot = TgBot(mock_config)
        bot._client = mock_telegram_client

        with patch("tgbot.client.asyncio.sleep", new_callable=AsyncMock):
            result = await bot.send_message("testchat", "Hello")

        assert result.ok is False
        assert result.error == "channel_private"
        assert result.retryable is False

    async def test_send_message_flood_wait(self, mock_config, mock_telegram_client):
        """Test send with flood wait error."""
        error = FloodWaitError(request=None, capture=0)
        error.seconds = 120
        mock_telegram_client.send_message = AsyncMock(side_effect=error)

        bot = TgBot(mock_config)
        bot._client = mock_telegram_client

        with patch("tgbot.client.asyncio.sleep", new_callable=AsyncMock):
            result = await bot.send_message("testchat", "Hello")

        assert result.ok is False
        assert result.error == "flood_wait"
        assert result.retryable is True
        assert result.wait_seconds == 120

    async def test_send_message_slow_mode(self, mock_config, mock_telegram_client):
        """Test send with slow mode wait error."""
        error = SlowModeWaitError(request=None, capture=0)
        error.seconds = 30
        mock_telegram_client.send_message = AsyncMock(side_effect=error)

        bot = TgBot(mock_config)
        bot._client = mock_telegram_client

        with patch("tgbot.client.asyncio.sleep", new_callable=AsyncMock):
            result = await bot.send_message("testchat", "Hello")

        assert result.ok is False
        assert result.error == "slow_mode"
        assert result.retryable is True
        assert result.wait_seconds == 30


class TestTgBotSendComment:
    """Tests for TgBot.send_comment() method."""

    async def test_send_comment_success(self, mock_config, mock_telegram_client):
        """Test successful comment send."""
        mock_msg = MagicMock()
        mock_msg.id = 888
        mock_telegram_client.send_message = AsyncMock(return_value=mock_msg)

        bot = TgBot(mock_config)
        bot._client = mock_telegram_client

        with patch("tgbot.client.asyncio.sleep", new_callable=AsyncMock):
            result = await bot.send_comment("channel", post_id=100, text="Nice post!")

        assert result.ok is True
        assert result.message_id == 888
        # When reply_to is None, uses comment_to without reply_to parameter
        mock_telegram_client.send_message.assert_called_once_with(
            "channel", "Nice post!", comment_to=100
        )

    async def test_send_comment_with_reply_to(self, mock_config, mock_telegram_client):
        """Test comment with reply_to for threading - sends to discussion group."""
        mock_msg = MagicMock()
        mock_msg.id = 889
        mock_telegram_client.send_message = AsyncMock(return_value=mock_msg)

        # Mock get_entity to return a channel entity
        mock_channel = MagicMock()
        mock_telegram_client.get_entity = AsyncMock(return_value=mock_channel)

        # Mock GetFullChannelRequest to return linked discussion group
        mock_full_chat = MagicMock()
        mock_full_chat.full_chat.linked_chat_id = 999  # Discussion group ID
        mock_telegram_client.return_value = mock_full_chat

        bot = TgBot(mock_config)
        bot._client = mock_telegram_client

        with patch("tgbot.client.asyncio.sleep", new_callable=AsyncMock):
            with patch("tgbot.client.GetFullChannelRequest") as mock_request:
                mock_telegram_client.__call__ = AsyncMock(return_value=mock_full_chat)
                result = await bot.send_comment(
                    "channel", post_id=100, text="Reply!", reply_to=555
                )

        assert result.ok is True
        # When reply_to is set, sends to discussion group with reply_to
        mock_telegram_client.send_message.assert_called_once_with(
            999, "Reply!", reply_to=555
        )

    async def test_send_comment_banned(self, mock_config, mock_telegram_client):
        """Test comment when banned."""
        mock_telegram_client.send_message = AsyncMock(
            side_effect=ChatWriteForbiddenError(request=None)
        )

        bot = TgBot(mock_config)
        bot._client = mock_telegram_client

        with patch("tgbot.client.asyncio.sleep", new_callable=AsyncMock):
            result = await bot.send_comment("channel", post_id=100, text="Test")

        assert result.ok is False
        assert result.error == "banned"
        assert result.retryable is False


class TestTgBotContextManager:
    """Tests for TgBot async context manager."""

    async def test_context_manager_connects_and_disconnects(self, mock_config):
        """Test that context manager properly connects and disconnects."""
        with patch.object(TgBot, "connect", new_callable=AsyncMock) as mock_connect:
            with patch.object(TgBot, "disconnect", new_callable=AsyncMock) as mock_disconnect:
                async with TgBot(mock_config) as bot:
                    mock_connect.assert_called_once()

                mock_disconnect.assert_called_once()

    async def test_context_manager_disconnects_on_exception(self, mock_config):
        """Test that disconnect is called even when exception occurs."""
        with patch.object(TgBot, "connect", new_callable=AsyncMock):
            with patch.object(TgBot, "disconnect", new_callable=AsyncMock) as mock_disconnect:
                with pytest.raises(ValueError):
                    async with TgBot(mock_config):
                        raise ValueError("Test error")

                mock_disconnect.assert_called_once()


class TestTgBotGetTargetType:
    """Tests for TgBot.get_target_type() method."""

    async def test_get_target_type_channel(self, mock_config, mock_telegram_client):
        """Test getting type for broadcast channel."""
        from telethon.tl.types import Channel

        mock_entity = MagicMock(spec=Channel)
        mock_entity.broadcast = True
        mock_telegram_client.get_entity = AsyncMock(return_value=mock_entity)

        bot = TgBot(mock_config)
        bot._client = mock_telegram_client

        result = await bot.get_target_type("testchannel")
        assert result == "channel"

    async def test_get_target_type_supergroup(self, mock_config, mock_telegram_client):
        """Test getting type for supergroup."""
        from telethon.tl.types import Channel

        mock_entity = MagicMock(spec=Channel)
        mock_entity.broadcast = False
        mock_telegram_client.get_entity = AsyncMock(return_value=mock_entity)

        bot = TgBot(mock_config)
        bot._client = mock_telegram_client

        result = await bot.get_target_type("testgroup")
        assert result == "supergroup"

    async def test_get_target_type_group(self, mock_config, mock_telegram_client):
        """Test getting type for basic group."""
        from telethon.tl.types import Chat

        mock_entity = MagicMock(spec=Chat)
        mock_telegram_client.get_entity = AsyncMock(return_value=mock_entity)

        bot = TgBot(mock_config)
        bot._client = mock_telegram_client

        result = await bot.get_target_type(12345)
        assert result == "group"

    async def test_get_target_type_error(self, mock_config, mock_telegram_client):
        """Test error handling when getting target type fails."""
        mock_telegram_client.get_entity = AsyncMock(side_effect=Exception("Not found"))

        bot = TgBot(mock_config)
        bot._client = mock_telegram_client

        with pytest.raises(TgBotError, match="Failed to get target type"):
            await bot.get_target_type("invalid")
