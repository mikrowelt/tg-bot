"""Tests for tgbot.verification.button module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telethon.errors import FloodWaitError

from tgbot.verification.button import ButtonVerification, VerificationError


class TestVerificationError:
    """Tests for VerificationError exception."""

    def test_verification_error_message(self):
        """Test VerificationError stores message."""
        error = VerificationError("Test error")
        assert str(error) == "Test error"

    def test_verification_error_inheritance(self):
        """Test VerificationError inherits from Exception."""
        assert issubclass(VerificationError, Exception)


class TestButtonVerificationInit:
    """Tests for ButtonVerification initialization."""

    def test_init_without_captcha_key(self):
        """Test initialization without captcha API key."""
        mock_client = MagicMock()
        verification = ButtonVerification(mock_client)

        assert verification.client == mock_client
        assert verification.captcha_solver is not None
        assert verification.pm_verification is not None

    def test_init_with_captcha_key(self):
        """Test initialization with captcha API key."""
        mock_client = MagicMock()
        verification = ButtonVerification(mock_client, captcha_api_key="test_key")

        assert verification.client == mock_client


class TestButtonVerificationVerify:
    """Tests for ButtonVerification.verify() method."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock Telegram client."""
        client = AsyncMock()
        return client

    @pytest.fixture
    def verification(self, mock_client):
        """Create ButtonVerification instance."""
        return ButtonVerification(mock_client)

    async def test_verify_no_bot_messages(self, verification, mock_client):
        """Test verify returns True when no bot messages found."""
        # Create a mock message from non-bot user
        mock_message = MagicMock()
        mock_sender = MagicMock()
        mock_sender.bot = False
        mock_message.get_sender = AsyncMock(return_value=mock_sender)

        mock_client.iter_messages = MagicMock(return_value=self._async_gen([mock_message]))

        result = await verification.verify(channel_id=123456)
        assert result is True

    async def test_verify_empty_channel(self, verification, mock_client):
        """Test verify returns True when channel has no messages."""
        mock_client.iter_messages = MagicMock(return_value=self._async_gen([]))

        result = await verification.verify(channel_id=123456)
        assert result is True

    async def test_verify_math_problem(self, verification, mock_client):
        """Test verify handles math problem from bot."""
        # Create a mock bot message with math problem
        mock_message = MagicMock()
        mock_message.message = "To verify you're human, solve: 5 + 3 = ?"
        mock_message.photo = None
        mock_message.reply_markup = None
        mock_message.reply = AsyncMock()

        mock_sender = MagicMock()
        mock_sender.bot = True
        mock_sender.first_name = "VerifyBot"
        mock_sender.username = "verify_bot"
        mock_message.get_sender = AsyncMock(return_value=mock_sender)

        mock_client.iter_messages = MagicMock(return_value=self._async_gen([mock_message]))

        with patch("tgbot.verification.button.asyncio.sleep", new_callable=AsyncMock):
            result = await verification.verify(channel_id=123456)

        assert result is True
        mock_message.reply.assert_called_once_with("8")

    async def test_verify_callback_button(self, verification, mock_client):
        """Test verify handles callback button from bot."""
        # Create a custom class to simulate KeyboardButtonCallback
        class KeyboardButtonCallback:
            def __init__(self):
                self.text = "I'm not a robot"
                self.data = b"verify"

        mock_button = KeyboardButtonCallback()

        # Create mock reply markup
        mock_row = MagicMock()
        mock_row.buttons = [mock_button]
        mock_markup = MagicMock()
        mock_markup.rows = [mock_row]

        # Create mock message
        mock_message = MagicMock()
        mock_message.message = "Click the button to verify"
        mock_message.photo = None
        mock_message.reply_markup = mock_markup
        mock_message.click = AsyncMock(return_value=MagicMock(message="Verified!"))

        mock_sender = MagicMock()
        mock_sender.bot = True
        mock_sender.first_name = "VerifyBot"
        mock_sender.username = "verify_bot"
        mock_message.get_sender = AsyncMock(return_value=mock_sender)

        mock_client.iter_messages = MagicMock(return_value=self._async_gen([mock_message]))

        with patch("tgbot.verification.button.asyncio.sleep", new_callable=AsyncMock):
            result = await verification.verify(channel_id=123456)

        assert result is True
        mock_message.click.assert_called_once_with(data=b"verify")

    async def test_verify_flood_wait_error(self, verification, mock_client):
        """Test verify handles FloodWaitError."""
        mock_message = MagicMock()
        mock_message.get_sender = AsyncMock(side_effect=FloodWaitError(request=None, capture=30))

        mock_client.iter_messages = MagicMock(return_value=self._async_gen([mock_message]))

        with pytest.raises(VerificationError) as exc_info:
            await verification.verify(channel_id=123456)

        assert "Rate limited" in str(exc_info.value)

    async def test_verify_generic_error(self, verification, mock_client):
        """Test verify handles generic exceptions."""
        mock_client.iter_messages = MagicMock(side_effect=Exception("Network error"))

        with pytest.raises(VerificationError) as exc_info:
            await verification.verify(channel_id=123456)

        assert "Verification failed" in str(exc_info.value)

    async def test_verify_bot_without_verification(self, verification, mock_client):
        """Test verify returns True when bot has no verification requirements."""
        mock_message = MagicMock()
        mock_message.message = "Welcome to the channel!"  # No math problem
        mock_message.photo = None
        mock_message.reply_markup = None

        mock_sender = MagicMock()
        mock_sender.bot = True
        mock_sender.first_name = "WelcomeBot"
        mock_sender.username = "welcome_bot"
        mock_message.get_sender = AsyncMock(return_value=mock_sender)

        mock_client.iter_messages = MagicMock(return_value=self._async_gen([mock_message]))

        with patch("tgbot.verification.button.asyncio.sleep", new_callable=AsyncMock):
            result = await verification.verify(channel_id=123456)

        assert result is True

    async def test_verify_uses_message_limit(self, verification, mock_client):
        """Test verify uses correct message limit."""
        mock_client.iter_messages = MagicMock(return_value=self._async_gen([]))

        await verification.verify(channel_id=123456, limit=10)

        mock_client.iter_messages.assert_called_once_with(123456, limit=10)

    async def test_verify_default_limit(self, verification, mock_client):
        """Test verify uses default limit of 5."""
        mock_client.iter_messages = MagicMock(return_value=self._async_gen([]))

        await verification.verify(channel_id=123456)

        mock_client.iter_messages.assert_called_once_with(123456, limit=5)

    @staticmethod
    async def _async_gen(items):
        """Helper to create async generator from list."""
        for item in items:
            yield item


class TestButtonVerificationCaptcha:
    """Tests for captcha handling in ButtonVerification."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock Telegram client."""
        client = AsyncMock()
        return client

    async def test_captcha_solving_attempted(self, mock_client):
        """Test that captcha solving is attempted when photo present."""
        verification = ButtonVerification(mock_client, captcha_api_key="test_key")

        # Mock captcha solver
        verification.captcha_solver.solve = AsyncMock(return_value="ABC123")

        # Create mock message with photo
        mock_message = MagicMock()
        mock_message.message = "Solve the captcha"
        mock_message.photo = MagicMock()  # Has photo
        mock_message.reply_markup = None
        mock_message.reply = AsyncMock()

        mock_sender = MagicMock()
        mock_sender.bot = True
        mock_sender.first_name = "CaptchaBot"
        mock_sender.username = "captcha_bot"
        mock_message.get_sender = AsyncMock(return_value=mock_sender)

        mock_client.iter_messages = MagicMock(
            return_value=TestButtonVerificationVerify._async_gen([mock_message])
        )
        mock_client.download_media = AsyncMock(return_value=b"fake_image_bytes")

        with patch("tgbot.verification.button.asyncio.sleep", new_callable=AsyncMock):
            result = await verification.verify(channel_id=123456)

        assert result is True
        mock_message.reply.assert_called_once_with("ABC123")
