"""
Configuration module using Pydantic for validation.

This module provides Config and ProxyConfig classes for loading
and validating tg-bot configuration from environment variables
and profile JSON files.
"""
import os
import json
import socks
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from dotenv import load_dotenv

from .logger import setup_logger

load_dotenv()

log = setup_logger("tg-bot.config")


class ConfigError(Exception):
    """Raised when configuration is invalid or missing."""
    pass


class ProxyConfig(BaseModel):
    """Proxy configuration with validation."""

    model_config = {"frozen": False}

    type: int = Field(description="Proxy type (socks.SOCKS5, socks.SOCKS4, socks.HTTP)")
    host: str = Field(min_length=1, description="Proxy host")
    port: int = Field(ge=1, le=65535, description="Proxy port")
    username: str | None = Field(default=None, description="Proxy username")
    password: str | None = Field(default=None, description="Proxy password")

    def to_tuple(self) -> tuple:
        """Convert to tuple format expected by Telethon."""
        if self.username and self.password:
            return (self.type, self.host, self.port, True, self.username, self.password)
        if self.username or self.password:
            raise ConfigError("Proxy requires both username and password, or neither")
        return (self.type, self.host, self.port)

    def __str__(self) -> str:
        type_names = {socks.SOCKS5: "SOCKS5", socks.SOCKS4: "SOCKS4", socks.HTTP: "HTTP"}
        return f"{type_names.get(self.type, 'UNKNOWN')}://{self.host}:{self.port}"


class Config(BaseModel):
    """
    Main configuration model with Pydantic validation.

    Loads configuration from:
    - Environment variables (proxy, captcha key, base dir)
    - Profile JSON file (Telegram credentials)
    """

    # Paths
    profile_path: Path = Field(description="Path to the profile JSON file")
    session_path: Path = Field(description="Path to the session file (without extension)")

    # Captcha
    captcha_api_key: str | None = Field(default=None, description="2Captcha API key")

    # Proxy
    proxy: ProxyConfig | None = Field(default=None, description="Proxy configuration")

    # Profile data (loaded from JSON)
    app_id: int = Field(gt=0, description="Telegram app ID")
    app_hash: str = Field(min_length=1, description="Telegram app hash")
    phone: str = Field(min_length=1, description="Phone number (digits only)")
    device: str = Field(default="Unknown", description="Device model")
    sdk: str = Field(default="Windows 10", description="SDK version")
    app_version: str = Field(default="1.0.0", description="App version")
    lang_pack: str = Field(default="en", description="Language pack")
    two_fa: str | None = Field(default=None, description="2FA password")

    @field_validator('phone', mode='before')
    @classmethod
    def convert_phone_to_string(cls, v):
        """Ensure phone is always a string."""
        return str(v) if v is not None else v

    @field_validator('app_id', mode='before')
    @classmethod
    def convert_app_id_to_int(cls, v):
        """Ensure app_id is always an int."""
        return int(v) if v is not None else v

    model_config = {"frozen": False, "arbitrary_types_allowed": True}

    @classmethod
    def load(cls, profile_name: str | None = None) -> "Config":
        """
        Load configuration from environment and profile JSON.

        Args:
            profile_name: Name of the profile (without .json extension).
                         Defaults to PROFILE_NAME env var or "profile".

        Returns:
            Validated Config instance

        Raises:
            ConfigError: If profile file is missing or invalid
        """
        # Determine profile name
        profile_name = profile_name or os.getenv("PROFILE_NAME", "profile")
        log.debug(f"Loading profile: {profile_name}")

        # Paths
        base_dir = Path(os.getenv("BASE_DIR", "."))
        profile_path = base_dir / f"{profile_name}.json"
        session_path = base_dir / profile_name

        if not profile_path.exists():
            log.error(f"Profile file not found: {profile_path}")
            raise ConfigError(f"Profile file not found: {profile_path}")

        # Load profile JSON
        try:
            with open(profile_path, "r") as f:
                profile_data = json.load(f)
            log.debug(f"Loaded profile data from {profile_path}")
        except json.JSONDecodeError as e:
            log.error(f"Invalid JSON in profile file: {e}")
            raise ConfigError(f"Invalid JSON in profile file: {e}")

        # Captcha API key
        captcha_api_key = os.getenv("CAPTCHA_API_KEY", "")
        if captcha_api_key:
            log.debug("Captcha API key configured")

        # Proxy configuration
        proxy = cls._load_proxy()

        # Validate required fields
        required_fields = ["app_id", "app_hash", "phone"]
        for field in required_fields:
            if not profile_data.get(field):
                log.error(f"Missing required field in profile: {field}")
                raise ConfigError(f"Missing required field in profile: {field}")

        try:
            config = cls(
                profile_path=profile_path,
                session_path=session_path,
                captcha_api_key=captcha_api_key if captcha_api_key else None,
                proxy=proxy,
                app_id=profile_data["app_id"],
                app_hash=profile_data["app_hash"],
                phone=str(profile_data["phone"]),
                device=profile_data.get("device", "Unknown"),
                sdk=profile_data.get("sdk", "Windows 10"),
                app_version=profile_data.get("app_version", "1.0.0"),
                lang_pack=profile_data.get("lang_pack", "en"),
                two_fa=profile_data.get("twoFA") or profile_data.get("two_fa"),
            )
        except Exception as e:
            log.error(f"Configuration validation failed: {e}")
            raise ConfigError(f"Configuration validation failed: {e}")

        log.info(f"Configuration loaded for phone: +{config.phone[-4:].rjust(len(config.phone), '*')}")
        return config

    @classmethod
    def _load_proxy(cls) -> ProxyConfig | None:
        """Load proxy configuration from environment variables."""
        proxy_type = os.getenv("PROXY_TYPE", "").upper()
        proxy_host = os.getenv("PROXY_HOST", "")
        proxy_port = os.getenv("PROXY_PORT", "")

        if not (proxy_type and proxy_host and proxy_port):
            return None

        proxy_type_map = {
            "SOCKS5": socks.SOCKS5,
            "SOCKS4": socks.SOCKS4,
            "HTTP": socks.HTTP,
        }

        if proxy_type not in proxy_type_map:
            log.error(f"Invalid proxy type: {proxy_type}")
            raise ConfigError(f"Invalid proxy type: {proxy_type}")

        try:
            proxy_port_int = int(proxy_port)
        except ValueError:
            log.error(f"Invalid proxy port: {proxy_port}")
            raise ConfigError(f"Invalid proxy port (must be integer): {proxy_port}")

        try:
            proxy = ProxyConfig(
                type=proxy_type_map[proxy_type],
                host=proxy_host,
                port=proxy_port_int,
                username=os.getenv("PROXY_USERNAME"),
                password=os.getenv("PROXY_PASSWORD"),
            )
        except Exception as e:
            log.error(f"Proxy configuration validation failed: {e}")
            raise ConfigError(f"Proxy configuration validation failed: {e}")

        log.debug(f"Proxy configured: {proxy}")
        return proxy
