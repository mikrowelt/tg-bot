# Configuration

## Environment Variables

### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `PROFILE_NAME` | Profile file name (no extension) | `profile` |
| `BASE_DIR` | Directory containing profiles | `.` |

### Proxy

| Variable | Description | Values |
|----------|-------------|--------|
| `PROXY_TYPE` | Proxy protocol | `SOCKS5`, `SOCKS4`, `HTTP` |
| `PROXY_HOST` | Proxy server host | `proxy.example.com` |
| `PROXY_PORT` | Proxy server port | `1080` |
| `PROXY_USERNAME` | Auth username (optional) | |
| `PROXY_PASSWORD` | Auth password (optional) | |

All proxy variables must be set together (except username/password).

### External Services

| Variable | Description | Required For |
|----------|-------------|--------------|
| `CAPTCHA_API_KEY` | 2Captcha API key | Image captcha solving |
| `ANTHROPIC_API_KEY` | Claude API key | AI verification |
| `REDIS_URL` | Redis connection URL | Worker, listener |

### Monitoring

| Variable | Description |
|----------|-------------|
| `LOG_LEVEL` | DEBUG, INFO, WARNING, ERROR |
| `LOG_FORMAT` | simple, detailed, json |
| `ENVIRONMENT` | Environment label for metrics |
| `GRAFANA_CLOUD_USER` | Grafana instance ID |
| `GRAFANA_CLOUD_API_KEY` | Grafana API key |
| `PROMETHEUS_PUSH_GATEWAY` | Prometheus push gateway URL |
| `LOKI_URL` | Loki log ingestion URL |

### Worker & Listener

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379` | Redis connection |
| `RESULT_TTL` | `300` | Task result TTL (seconds) |

## Profile JSON

**Location:** `{BASE_DIR}/{PROFILE_NAME}.json`

```json
{
  "app_id": 123456,
  "app_hash": "abc123def456789...",
  "phone": "1234567890",
  "device": "Samsung Galaxy S21",
  "sdk": "SDK 31",
  "app_version": "8.9.0",
  "lang_pack": "en",
  "two_fa": "optional_password"
}
```

### Fields

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `app_id` | int | Yes | - | From my.telegram.org |
| `app_hash` | string | Yes | - | From my.telegram.org |
| `phone` | string | Yes | - | Phone number (digits only) |
| `device` | string | No | `"Unknown"` | Device model |
| `sdk` | string | No | `"Windows 10"` | SDK version |
| `app_version` | string | No | `"1.0.0"` | App version |
| `lang_pack` | string | No | `"en"` | Language code |
| `two_fa` | string | No | null | 2FA password |
| `twoFA` | string | No | null | Alias for two_fa |

### Getting Telegram Credentials

1. Go to https://my.telegram.org
2. Log in with your phone number
3. Go to "API development tools"
4. Create a new application
5. Copy `App api_id` and `App api_hash`

## Session File

**Location:** `{BASE_DIR}/{PROFILE_NAME}.session`

SQLite database created by Telethon containing:
- Authentication state
- Entity cache
- Message drafts

**Security:** Contains sensitive auth tokens. Protect with file permissions.

## Configuration Loading

### Load Order

1. Load `.env` file (python-dotenv)
2. Read environment variables
3. Parse profile JSON
4. Validate with Pydantic

### Example

```python
from tgbot.utils.config import Config

# Load default profile
config = Config.load()  # Uses PROFILE_NAME env var

# Load specific profile
config = Config.load("myprofile")

# Access fields
print(config.phone)
print(config.app_id)
print(config.proxy)  # ProxyConfig or None
```

### Validation Errors

```python
from tgbot.utils.config import ConfigError

try:
    config = Config.load("missing")
except ConfigError as e:
    print(f"Config error: {e}")
    # "Profile file not found: missing.json"
    # "Missing required field in profile: app_id"
    # "Invalid proxy type: UNKNOWN"
```

## Proxy Configuration

### SOCKS5 Example

```bash
export PROXY_TYPE=SOCKS5
export PROXY_HOST=proxy.example.com
export PROXY_PORT=1080
export PROXY_USERNAME=user
export PROXY_PASSWORD=pass
```

### HTTP Example

```bash
export PROXY_TYPE=HTTP
export PROXY_HOST=http-proxy.example.com
export PROXY_PORT=8080
```

### No Proxy

Simply don't set any `PROXY_*` variables.

## Timing Configuration

Constants in `utils/constants.py`:

```python
# Anti-detection delays (seconds)
WAIT_TINY = (0.5, 1.5)      # Button clicks
WAIT_SHORT = (1, 2)         # Quick ops
WAIT_NORMAL = (1, 3)        # Standard ops
WAIT_MEDIUM = (2, 4)        # After messages
WAIT_HUMAN = (3, 6)         # Human-like

# Fixed delays
DELAY_POLL = 0.1            # Polling loops
DELAY_PAGINATION = 0.5      # Pagination
DELAY_RETRY = 2             # Retry backoff

# Timeouts
TIMEOUT_OPERATION = 30      # Default ops
TIMEOUT_VERIFICATION = 60   # Verification
TIMEOUT_CAPTCHA = 120       # Captcha solving

# Retry
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 30     # Exponential backoff
```

## Docker Configuration

### Environment File

```env
# .env
PROFILE_NAME=profile
BASE_DIR=/profiles
REDIS_URL=redis://redis:6379
CAPTCHA_API_KEY=xxx
ANTHROPIC_API_KEY=sk-xxx
LOG_LEVEL=INFO
```

### Volume Mounts

```yaml
volumes:
  - ./profiles:/profiles:ro   # Profile JSON + session
```

### Example docker-compose

```yaml
services:
  tg-bot:
    image: tg-bot:latest
    env_file: .env
    volumes:
      - ./profiles:/profiles:ro
    command: worker --profiles profile1,profile2
    depends_on:
      - redis

  redis:
    image: redis:7-alpine
```
