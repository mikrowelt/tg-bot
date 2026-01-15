"""Shared fixtures for tests."""

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def tmp_profile(tmp_path: Path) -> Path:
    """Create a temporary profile JSON file."""
    profile_data = {
        "app_id": 123456,
        "app_hash": "test_app_hash_abc123",
        "phone": "1234567890",
        "device": "Test Device",
        "sdk": "Test SDK",
        "app_version": "1.0.0",
        "lang_pack": "en",
        "twoFA": "test2fa",
    }
    profile_path = tmp_path / "test_profile.json"
    profile_path.write_text(json.dumps(profile_data))
    return profile_path


@pytest.fixture
def profile_data() -> dict:
    """Return sample profile data."""
    return {
        "app_id": 123456,
        "app_hash": "test_app_hash_abc123",
        "phone": "1234567890",
        "device": "Test Device",
        "sdk": "Test SDK",
        "app_version": "1.0.0",
        "lang_pack": "en",
        "twoFA": "test2fa",
    }


@pytest.fixture
def mock_telegram_client():
    """Create a mock TelegramClient."""
    client = AsyncMock()

    # Mock user info
    mock_user = MagicMock()
    mock_user.id = 12345
    mock_user.first_name = "Test"
    mock_user.last_name = "User"
    mock_user.username = "testuser"
    mock_user.phone = "1234567890"
    mock_user.photo = None
    mock_user.restricted = False
    mock_user.deleted = False
    mock_user.fake = False
    mock_user.scam = False
    mock_user.restriction_reason = None

    client.get_me = AsyncMock(return_value=mock_user)
    client.is_user_authorized = AsyncMock(return_value=True)
    client.is_connected = MagicMock(return_value=True)
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.send_message = AsyncMock()

    return client


@pytest.fixture
def mock_config(tmp_profile: Path):
    """Create a mock Config object."""
    from tgbot.utils.config import Config, ProxyConfig

    return Config(
        profile_path=tmp_profile,
        session_path=tmp_profile.parent / "test_profile",
        captcha_api_key=None,
        proxy=None,
        app_id=123456,
        app_hash="test_app_hash_abc123",
        phone="1234567890",
        device="Test Device",
        sdk="Test SDK",
        app_version="1.0.0",
        lang_pack="en",
        two_fa="test2fa",
    )
