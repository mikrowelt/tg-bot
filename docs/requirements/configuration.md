# Configuration System

## Overview

Pydantic-based configuration management for tg-bot. Loads settings from environment variables and profile JSON files.

## Classes

### `Config`

Main configuration model with validation.

```python
class Config(BaseModel):
    """Main configuration model with Pydantic validation."""

    # Paths
    profile_path: Path       # Path to profile JSON file
    session_path: Path       # Path to session file (without extension)

    # External services
    captcha_api_key: str | None   # 2Captcha API key

    # Proxy
    proxy: ProxyConfig | None     # Proxy configuration

    # Telegram credentials (from profile JSON)
    app_id: int              # Telegram app ID
    app_hash: str            # Telegram app hash
    phone: str               # Phone number
    device: str              # Device model
    sdk: str                 # SDK version
    app_version: str         # App version
    lang_pack: str           # Language pack
    two_fa: str | None       # 2FA password
```

### Key Methods

```python
@classmethod
def load(cls, profile_name: str | None = None) -> Config:
    """
    Load configuration from environment and profile JSON.

    Args:
        profile_name: Profile name (without .json). Defaults to PROFILE_NAME env.

    Returns:
        Validated Config instance

    Raises:
        ConfigError: If profile file missing or invalid
    """
```

```python
@classmethod
def _load_proxy(cls) -> ProxyConfig | None:
    """Load proxy configuration from environment variables."""
```

### `ProxyConfig`

Proxy settings with validation.

```python
class ProxyConfig(BaseModel):
    """Proxy configuration with validation."""

    type: int      # socks.SOCKS5, socks.SOCKS4, or socks.HTTP
    host: str      # Proxy host
    port: int      # Proxy port (1-65535)
    username: str | None   # Proxy username (optional)
    password: str | None   # Proxy password (optional)
```

### Key Methods

```python
def to_tuple(self) -> tuple:
    """Convert to tuple format expected by Telethon."""
```

### `ConfigError`

```python
class ConfigError(Exception):
    """Raised when configuration is invalid or missing."""
```

## Environment Variables

### Required

| Variable | Description | Default |
|----------|-------------|---------|
| `PROFILE_NAME` | Profile file name (without .json) | `"profile"` |
| `BASE_DIR` | Directory containing profile files | `"."` |

### Optional

| Variable | Description | Default |
|----------|-------------|---------|
| `CAPTCHA_API_KEY` | 2Captcha API key for image captchas | None |
| `ANTHROPIC_API_KEY` | Anthropic API key for AI verification | None |
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379` |

### Proxy Configuration

| Variable | Description | Values |
|----------|-------------|--------|
| `PROXY_TYPE` | Proxy protocol | `SOCKS5`, `SOCKS4`, `HTTP` |
| `PROXY_HOST` | Proxy server hostname | Any hostname |
| `PROXY_PORT` | Proxy server port | 1-65535 |
| `PROXY_USERNAME` | Proxy auth username | Optional |
| `PROXY_PASSWORD` | Proxy auth password | Optional |

## Profile JSON Format

```json
{
  "app_id": 12345678,
  "app_hash": "abcdef1234567890",
  "phone": "79001234567",
  "device": "Samsung Galaxy S21",
  "sdk": "Android 12",
  "app_version": "9.4.0",
  "lang_pack": "en",
  "twoFA": "optional_2fa_password"
}
```

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `app_id` | int | Telegram API app ID |
| `app_hash` | string | Telegram API app hash |
| `phone` | string | Phone number (digits only) |

### Optional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `device` | string | `"Unknown"` | Device model for session |
| `sdk` | string | `"Windows 10"` | SDK version |
| `app_version` | string | `"1.0.0"` | App version |
| `lang_pack` | string | `"en"` | Language pack |
| `twoFA` / `two_fa` | string | None | 2FA password |

## Usage Examples

### Loading Configuration

```python
from tgbot.utils.config import Config, ConfigError

# Load default profile
config = Config.load()

# Load specific profile
config = Config.load("my_account")

# Access configuration
print(config.phone)
print(config.proxy)
```

### With TgBot Client

```python
from tgbot.client import TgBot
from tgbot.utils.config import Config

config = Config.load("my_account")
async with TgBot(config) as bot:
    await bot.health_check()
```

## Error Handling

```python
from tgbot.utils.config import Config, ConfigError

try:
    config = Config.load("nonexistent")
except ConfigError as e:
    print(f"Configuration error: {e}")
    # Possible errors:
    # - "Profile file not found: /path/to/nonexistent.json"
    # - "Missing required field in profile: app_id"
    # - "Invalid JSON in profile file: ..."
    # - "Invalid proxy type: INVALID"
```

## File Locations

| File | Location | Purpose |
|------|----------|---------|
| Profile JSON | `{BASE_DIR}/{PROFILE_NAME}.json` | Telegram credentials |
| Session file | `{BASE_DIR}/{PROFILE_NAME}.session` | Telethon session |

## Validation

Pydantic validates:
- `app_id` > 0
- `app_hash` non-empty
- `phone` non-empty (converted to string)
- `port` in range 1-65535
- Proxy requires both username+password or neither
