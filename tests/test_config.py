"""Tests for tgbot.utils.config module."""

import json
import os
import pytest
import socks
from pathlib import Path
from unittest.mock import patch

from tgbot.utils.config import Config, ConfigError, ProxyConfig


class TestProxyConfig:
    """Tests for ProxyConfig dataclass."""

    def test_to_tuple_without_auth(self):
        """Test to_tuple without username/password."""
        proxy = ProxyConfig(
            type=socks.SOCKS5,
            host="proxy.example.com",
            port=1080,
        )
        result = proxy.to_tuple()
        assert result == (socks.SOCKS5, "proxy.example.com", 1080)

    def test_to_tuple_with_auth(self):
        """Test to_tuple with username/password."""
        proxy = ProxyConfig(
            type=socks.SOCKS5,
            host="proxy.example.com",
            port=1080,
            username="user",
            password="pass",
        )
        result = proxy.to_tuple()
        assert result == (socks.SOCKS5, "proxy.example.com", 1080, True, "user", "pass")

    def test_to_tuple_username_only_raises(self):
        """Test that to_tuple raises error when only username is set."""
        proxy = ProxyConfig(
            type=socks.SOCKS5,
            host="proxy.example.com",
            port=1080,
            username="user",
            password=None,
        )
        with pytest.raises(ConfigError, match="both username and password"):
            proxy.to_tuple()

    def test_to_tuple_password_only_raises(self):
        """Test that to_tuple raises error when only password is set."""
        proxy = ProxyConfig(
            type=socks.SOCKS5,
            host="proxy.example.com",
            port=1080,
            username=None,
            password="pass",
        )
        with pytest.raises(ConfigError, match="both username and password"):
            proxy.to_tuple()

    def test_str_socks5(self):
        """Test string representation for SOCKS5."""
        proxy = ProxyConfig(type=socks.SOCKS5, host="localhost", port=1080)
        assert str(proxy) == "SOCKS5://localhost:1080"

    def test_str_socks4(self):
        """Test string representation for SOCKS4."""
        proxy = ProxyConfig(type=socks.SOCKS4, host="localhost", port=1080)
        assert str(proxy) == "SOCKS4://localhost:1080"

    def test_str_http(self):
        """Test string representation for HTTP."""
        proxy = ProxyConfig(type=socks.HTTP, host="localhost", port=8080)
        assert str(proxy) == "HTTP://localhost:8080"


class TestConfigLoad:
    """Tests for Config.load() method."""

    def test_load_basic_profile(self, tmp_path: Path):
        """Test loading a basic profile without proxy."""
        profile_data = {
            "app_id": 123456,
            "app_hash": "abc123",
            "phone": "1234567890",
        }
        profile_path = tmp_path / "test.json"
        profile_path.write_text(json.dumps(profile_data))

        env = {
            "BASE_DIR": str(tmp_path),
            "PROXY_TYPE": "",
            "PROXY_HOST": "",
            "PROXY_PORT": "",
        }
        with patch.dict(os.environ, env, clear=False):
            config = Config.load("test")

        assert config.app_id == 123456
        assert config.app_hash == "abc123"
        assert config.phone == "1234567890"
        assert config.proxy is None
        assert config.profile_path == profile_path
        assert config.session_path == tmp_path / "test"

    def test_load_profile_with_all_fields(self, tmp_path: Path):
        """Test loading a profile with all optional fields."""
        profile_data = {
            "app_id": 123456,
            "app_hash": "abc123",
            "phone": "1234567890",
            "device": "iPhone 15",
            "sdk": "iOS 17",
            "app_version": "10.0.0",
            "lang_pack": "ru",
            "twoFA": "secret123",
        }
        profile_path = tmp_path / "full.json"
        profile_path.write_text(json.dumps(profile_data))

        with patch.dict(os.environ, {"BASE_DIR": str(tmp_path)}, clear=False):
            config = Config.load("full")

        assert config.device == "iPhone 15"
        assert config.sdk == "iOS 17"
        assert config.app_version == "10.0.0"
        assert config.lang_pack == "ru"
        assert config.two_fa == "secret123"

    def test_load_profile_with_two_fa_alternative_key(self, tmp_path: Path):
        """Test loading two_fa with alternative key name."""
        profile_data = {
            "app_id": 123456,
            "app_hash": "abc123",
            "phone": "1234567890",
            "two_fa": "secret456",
        }
        profile_path = tmp_path / "alt.json"
        profile_path.write_text(json.dumps(profile_data))

        with patch.dict(os.environ, {"BASE_DIR": str(tmp_path)}, clear=False):
            config = Config.load("alt")

        assert config.two_fa == "secret456"

    def test_load_with_socks5_proxy(self, tmp_path: Path):
        """Test loading config with SOCKS5 proxy."""
        profile_data = {
            "app_id": 123456,
            "app_hash": "abc123",
            "phone": "1234567890",
        }
        profile_path = tmp_path / "proxy.json"
        profile_path.write_text(json.dumps(profile_data))

        env = {
            "BASE_DIR": str(tmp_path),
            "PROXY_TYPE": "SOCKS5",
            "PROXY_HOST": "proxy.example.com",
            "PROXY_PORT": "1080",
            "PROXY_USERNAME": "proxyuser",
            "PROXY_PASSWORD": "proxypass",
        }

        with patch.dict(os.environ, env, clear=False):
            config = Config.load("proxy")

        assert config.proxy is not None
        assert config.proxy.type == socks.SOCKS5
        assert config.proxy.host == "proxy.example.com"
        assert config.proxy.port == 1080
        assert config.proxy.username == "proxyuser"
        assert config.proxy.password == "proxypass"

    def test_load_with_http_proxy(self, tmp_path: Path):
        """Test loading config with HTTP proxy."""
        profile_data = {
            "app_id": 123456,
            "app_hash": "abc123",
            "phone": "1234567890",
        }
        profile_path = tmp_path / "http.json"
        profile_path.write_text(json.dumps(profile_data))

        env = {
            "BASE_DIR": str(tmp_path),
            "PROXY_TYPE": "HTTP",
            "PROXY_HOST": "http-proxy.example.com",
            "PROXY_PORT": "8080",
            "PROXY_USERNAME": "",
            "PROXY_PASSWORD": "",
        }

        with patch.dict(os.environ, env, clear=False):
            config = Config.load("http")

        assert config.proxy is not None
        assert config.proxy.type == socks.HTTP
        assert config.proxy.host == "http-proxy.example.com"
        assert config.proxy.port == 8080
        # Empty strings are falsy, so auth won't be used in to_tuple()
        assert not config.proxy.username
        assert not config.proxy.password

    def test_load_with_captcha_api_key(self, tmp_path: Path):
        """Test loading config with captcha API key."""
        profile_data = {
            "app_id": 123456,
            "app_hash": "abc123",
            "phone": "1234567890",
        }
        profile_path = tmp_path / "captcha.json"
        profile_path.write_text(json.dumps(profile_data))

        env = {
            "BASE_DIR": str(tmp_path),
            "CAPTCHA_API_KEY": "2captcha_key_123",
        }

        with patch.dict(os.environ, env, clear=False):
            config = Config.load("captcha")

        assert config.captcha_api_key == "2captcha_key_123"

    def test_load_profile_not_found(self, tmp_path: Path):
        """Test that ConfigError is raised when profile file doesn't exist."""
        with patch.dict(os.environ, {"BASE_DIR": str(tmp_path)}, clear=False):
            with pytest.raises(ConfigError, match="Profile file not found"):
                Config.load("nonexistent")

    def test_load_invalid_json(self, tmp_path: Path):
        """Test that ConfigError is raised for invalid JSON."""
        profile_path = tmp_path / "invalid.json"
        profile_path.write_text("not valid json {")

        with patch.dict(os.environ, {"BASE_DIR": str(tmp_path)}, clear=False):
            with pytest.raises(ConfigError, match="Invalid JSON"):
                Config.load("invalid")

    def test_load_missing_required_field_app_id(self, tmp_path: Path):
        """Test that ConfigError is raised when app_id is missing."""
        profile_data = {
            "app_hash": "abc123",
            "phone": "1234567890",
        }
        profile_path = tmp_path / "missing.json"
        profile_path.write_text(json.dumps(profile_data))

        with patch.dict(os.environ, {"BASE_DIR": str(tmp_path)}, clear=False):
            with pytest.raises(ConfigError, match="Missing required field.*app_id"):
                Config.load("missing")

    def test_load_missing_required_field_app_hash(self, tmp_path: Path):
        """Test that ConfigError is raised when app_hash is missing."""
        profile_data = {
            "app_id": 123456,
            "phone": "1234567890",
        }
        profile_path = tmp_path / "no_hash.json"
        profile_path.write_text(json.dumps(profile_data))

        with patch.dict(os.environ, {"BASE_DIR": str(tmp_path)}, clear=False):
            with pytest.raises(ConfigError, match="Missing required field.*app_hash"):
                Config.load("no_hash")

    def test_load_missing_required_field_phone(self, tmp_path: Path):
        """Test that ConfigError is raised when phone is missing."""
        profile_data = {
            "app_id": 123456,
            "app_hash": "abc123",
        }
        profile_path = tmp_path / "no_phone.json"
        profile_path.write_text(json.dumps(profile_data))

        with patch.dict(os.environ, {"BASE_DIR": str(tmp_path)}, clear=False):
            with pytest.raises(ConfigError, match="Missing required field.*phone"):
                Config.load("no_phone")

    def test_load_invalid_proxy_type(self, tmp_path: Path):
        """Test that ConfigError is raised for invalid proxy type."""
        profile_data = {
            "app_id": 123456,
            "app_hash": "abc123",
            "phone": "1234567890",
        }
        profile_path = tmp_path / "bad_proxy.json"
        profile_path.write_text(json.dumps(profile_data))

        env = {
            "BASE_DIR": str(tmp_path),
            "PROXY_TYPE": "INVALID",
            "PROXY_HOST": "proxy.example.com",
            "PROXY_PORT": "1080",
        }

        with patch.dict(os.environ, env, clear=False):
            with pytest.raises(ConfigError, match="Invalid proxy type"):
                Config.load("bad_proxy")

    def test_load_invalid_proxy_port(self, tmp_path: Path):
        """Test that ConfigError is raised for invalid proxy port."""
        profile_data = {
            "app_id": 123456,
            "app_hash": "abc123",
            "phone": "1234567890",
        }
        profile_path = tmp_path / "bad_port.json"
        profile_path.write_text(json.dumps(profile_data))

        env = {
            "BASE_DIR": str(tmp_path),
            "PROXY_TYPE": "SOCKS5",
            "PROXY_HOST": "proxy.example.com",
            "PROXY_PORT": "not_a_number",
        }

        with patch.dict(os.environ, env, clear=False):
            with pytest.raises(ConfigError, match="Invalid proxy port"):
                Config.load("bad_port")

    def test_load_uses_profile_name_env_var(self, tmp_path: Path):
        """Test that PROFILE_NAME env var is used when profile_name not provided."""
        profile_data = {
            "app_id": 123456,
            "app_hash": "abc123",
            "phone": "1234567890",
        }
        profile_path = tmp_path / "env_profile.json"
        profile_path.write_text(json.dumps(profile_data))

        env = {
            "BASE_DIR": str(tmp_path),
            "PROFILE_NAME": "env_profile",
        }

        with patch.dict(os.environ, env, clear=False):
            config = Config.load()

        assert config.app_id == 123456

    def test_load_default_values(self, tmp_path: Path):
        """Test that default values are used for optional fields."""
        profile_data = {
            "app_id": 123456,
            "app_hash": "abc123",
            "phone": "1234567890",
        }
        profile_path = tmp_path / "defaults.json"
        profile_path.write_text(json.dumps(profile_data))

        with patch.dict(os.environ, {"BASE_DIR": str(tmp_path)}, clear=False):
            config = Config.load("defaults")

        assert config.device == "Unknown"
        assert config.sdk == "Windows 10"
        assert config.app_version == "1.0.0"
        assert config.lang_pack == "en"
        assert config.two_fa is None

    def test_phone_converted_to_string(self, tmp_path: Path):
        """Test that phone number is converted to string."""
        profile_data = {
            "app_id": 123456,
            "app_hash": "abc123",
            "phone": 1234567890,  # Integer, not string
        }
        profile_path = tmp_path / "phone_int.json"
        profile_path.write_text(json.dumps(profile_data))

        with patch.dict(os.environ, {"BASE_DIR": str(tmp_path)}, clear=False):
            config = Config.load("phone_int")

        assert config.phone == "1234567890"
        assert isinstance(config.phone, str)
