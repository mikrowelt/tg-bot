import os
import json
import socks
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

from .logger import setup_logger

load_dotenv()

log = setup_logger("tg-bot.config")


class ConfigError(Exception):
    """Raised when configuration is invalid or missing."""
    pass


@dataclass
class ProxyConfig:
    type: int
    host: str
    port: int
    username: str | None = None
    password: str | None = None

    def to_tuple(self) -> tuple:
        if self.username and self.password:
            return (self.type, self.host, self.port, True, self.username, self.password)
        if self.username or self.password:
            raise ConfigError("Proxy requires both username and password, or neither")
        return (self.type, self.host, self.port)

    def __str__(self) -> str:
        type_names = {socks.SOCKS5: "SOCKS5", socks.SOCKS4: "SOCKS4", socks.HTTP: "HTTP"}
        return f"{type_names.get(self.type, 'UNKNOWN')}://{self.host}:{self.port}"


@dataclass
class Config:
    # Paths
    profile_path: Path
    session_path: Path

    # Captcha
    captcha_api_key: str | None

    # Proxy
    proxy: ProxyConfig | None

    # Profile data (loaded from JSON)
    app_id: int
    app_hash: str
    phone: str
    device: str
    sdk: str
    app_version: str
    lang_pack: str
    two_fa: str | None

    @classmethod
    def load(cls, profile_name: str | None = None) -> "Config":
        """Load configuration from environment and profile JSON."""
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
        proxy = None
        proxy_type = os.getenv("PROXY_TYPE", "").upper()
        proxy_host = os.getenv("PROXY_HOST", "")
        proxy_port = os.getenv("PROXY_PORT", "")

        if proxy_type and proxy_host and proxy_port:
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

            proxy = ProxyConfig(
                type=proxy_type_map[proxy_type],
                host=proxy_host,
                port=proxy_port_int,
                username=os.getenv("PROXY_USERNAME"),
                password=os.getenv("PROXY_PASSWORD"),
            )
            log.debug(f"Proxy configured: {proxy}")

        # Validate required fields
        required_fields = ["app_id", "app_hash", "phone"]
        for field in required_fields:
            if not profile_data.get(field):
                log.error(f"Missing required field in profile: {field}")
                raise ConfigError(f"Missing required field in profile: {field}")

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

        log.info(f"Configuration loaded for phone: +{config.phone[-4:].rjust(len(config.phone), '*')}")
        return config
