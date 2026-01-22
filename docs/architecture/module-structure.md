# Module Structure

## Package Layout

```
tgbot/
├── __init__.py
├── cli.py                    # Entry point, argument parsing
│
├── client.py                 # Main TgBot class (280 lines)
├── client_profile.py         # ProfileMixin (648 lines)
├── client_channels.py        # ChannelsMixin (311 lines)
├── client_messages.py        # MessagesMixin (359 lines)
├── client_info.py            # InfoMixin (463 lines)
│
├── commands/                 # CLI command implementations
│   ├── __init__.py
│   ├── base.py               # run_command wrapper
│   ├── join_channel.py
│   ├── send_message.py
│   ├── change_profile.py
│   ├── check_ban.py
│   ├── check_all_bans.py
│   ├── chat_info.py
│   ├── get_profile.py
│   ├── profile_health_check.py
│   └── health_check.py
│
├── verification/             # Bot verification handlers
│   ├── __init__.py
│   ├── button.py             # ButtonVerification
│   ├── captcha.py            # 2Captcha integration
│   ├── math_solver.py        # Math problem solver
│   ├── pm.py                 # PM verification
│   └── ai_agent.py           # AI verification (1020 lines)
│
├── worker/                   # Task queue system
│   ├── __init__.py
│   ├── dispatcher.py         # Queue monitor, subprocess spawner
│   ├── runner.py             # Single task executor
│   ├── handlers.py           # Command handlers
│   └── task.py               # Task/TaskResult dataclasses
│
├── listener/                 # Message monitoring
│   ├── __init__.py
│   ├── listener.py           # Telegram event handler
│   └── redis_stream.py       # Stream publishing, heartbeats
│
└── utils/                    # Shared utilities
    ├── __init__.py
    ├── config.py             # Pydantic Config/ProxyConfig
    ├── constants.py          # Timing constants
    ├── logger.py             # Logging setup
    ├── metrics.py            # Prometheus metrics
    ├── retry.py              # Retry utilities
    └── timeout.py            # Timeout utilities
```

## Import Graph

```
cli.py
  ├── commands/*
  │     └── base.py (run_command)
  │           └── client.py (TgBot)
  │
  ├── worker/dispatcher.py
  │     └── worker/runner.py
  │           └── worker/handlers.py
  │                 └── client.py (TgBot)
  │
  └── listener/listener.py
        └── listener/redis_stream.py

client.py (TgBot)
  ├── client_profile.py (ProfileMixin)
  ├── client_channels.py (ChannelsMixin)
  ├── client_messages.py (MessagesMixin)
  ├── client_info.py (InfoMixin)
  └── verification/button.py (ButtonVerification)
        ├── verification/math_solver.py
        ├── verification/captcha.py
        └── verification/pm.py
```

## Module Responsibilities

### Entry Point (`cli.py`)

- Define argparse subparsers for each command
- Configure logging based on options
- Route to command functions in `commands/`

### Client Core (`client.py`)

**Class: `TgBot`**

Inherits from all mixins, provides:
- `connect()` / `disconnect()` — Telegram connection lifecycle
- `health_check()` — Account status check
- `terminate_other_sessions()` — Session management
- Properties: `client`, `verification`, `ai_verification`

### Client Mixins

**ProfileMixin (`client_profile.py`)**
- `change_profile()` — Update name/bio/username/photo
- `set_username()` — Set username with retry
- `get_profile()` — Fetch profile data
- `profile_health_check()` — Validate against expected values
- `delete_all_profile_photos()` — Clear photo history
- `upload_multiple_photos()` — Batch upload
- `get_joined_channels()` — List memberships
- `get_profile_photos()` — Download photos

**ChannelsMixin (`client_channels.py`)**
- `join_channel()` — Join and verify
- `leave_channel()` — Leave channel
- `_join_linked_discussion()` — Join discussion group
- `_get_channel_id()` — Resolve ID from link

**MessagesMixin (`client_messages.py`)**
- `send_message()` — Send to chat/user
- `send_comment()` — Comment on post
- `verify_in_comments()` — Handle comment verification
- `send_reaction()` — React with emoji
- `_handle_send_error()` — Error classification

**InfoMixin (`client_info.py`)**
- `get_target_type()` — Determine chat type
- `check_channel_membership()` — Verify membership
- `get_latest_post()` — Fetch newest post
- `get_recent_posts()` — Fetch post history
- `get_channel_info()` — Full channel metadata
- `get_forum_topics()` — List forum topics
- `get_recent_messages_in_topic()` — Topic messages

### Commands (`commands/`)

Each command file exports an async function called by CLI:

```python
# commands/join_channel.py
async def join_channel_command(args):
    config = Config.load(args.profile)
    async with TgBot(config) as bot:
        channel_id = await bot.join_channel(args.channel)
        return {"channel_id": channel_id}
```

**base.py** provides `run_command()` wrapper:
- Configures logging
- Catches errors
- Formats JSON output

### Verification (`verification/`)

**ButtonVerification**
- Main verification orchestrator
- Delegates to specialized solvers

**MathSolver**
- Regex-based math extraction
- Arithmetic evaluation

**CaptchaSolver**
- 2Captcha API client
- Base64 image encoding
- Polling for solutions

**PMVerification**
- `/start` bot in PM
- Button click handling

**AIVerificationAgent**
- Claude API client
- Pattern fingerprinting
- Cache management

### Worker (`worker/`)

**Dispatcher**
- Redis queue monitoring (BLPOP)
- Subprocess management
- Graceful shutdown

**Runner**
- Task deserialization
- TgBot initialization
- Result storage

**Handlers**
- Command-to-method mapping
- Error wrapping

### Listener (`listener/`)

**Listener**
- Telethon event registration
- Group filtering
- Message extraction

**MessageStream / HeartbeatManager**
- Redis XADD publishing
- Heartbeat SETEX

### Utilities (`utils/`)

**config.py**
- `class Config(BaseModel)` — Main configuration model
- `class ProxyConfig(BaseModel)` — Proxy settings
- `class ConfigError(Exception)` — Configuration errors
- `Config.load(profile_name: str | None) -> Config` — Load from env/JSON
- `Config._load_proxy() -> ProxyConfig | None` — Load proxy from env
- `ProxyConfig.to_tuple() -> tuple` — Convert to Telethon format

**constants.py**
- `WAIT_TINY`, `WAIT_SHORT`, `WAIT_NORMAL` — Short delay ranges
- `WAIT_MEDIUM`, `WAIT_VERIFICATION`, `WAIT_HUMAN` — Medium delays
- `WAIT_LONG`, `WAIT_RATE_LIMIT_EXTRA` — Long delays
- `DELAY_POLL`, `DELAY_RETRY`, `DELAY_CAPTCHA_*` — Fixed delays
- `TIMEOUT_OPERATION`, `TIMEOUT_VERIFICATION`, `TIMEOUT_CAPTCHA`
- `MAX_RETRIES`, `RETRY_BACKOFF_BASE` — Retry config
- `random_wait(wait_range: Tuple[float, float]) -> float`

**logger.py**
- `class LogLevel(Enum)` — DEBUG, INFO, WARNING, ERROR
- `class JsonFormatter(logging.Formatter)` — Structured JSON logs
- `class LoggerAdapter(logging.LoggerAdapter)` — Context adapter
- `setup_logger(name: str) -> logging.Logger`
- `configure_loki(loki_url, username, password, additional_labels) -> bool`
- `get_logger_with_context(name: str, **context) -> LoggerAdapter`

**metrics.py**
- `configure_metrics(push_gateway_url, job_name, username, password) -> None`
- `push_metrics() -> bool` — Push to gateway
- `record_message_sent(status, target_type, duration)`
- `record_channel_join(status, duration)`
- `record_verification(verification_type, status)`
- `record_rate_limit(operation, wait_seconds)`
- `record_error(error_type, operation)`
- `record_profile_update(field, status)`
- `@track_duration(histogram, **labels)` — Duration decorator
- `@track_operation(operation_name)` — Active ops gauge

**retry.py**
- `class RetryExhaustedError(Exception)` — All retries failed
- `class RetryContext` — Manual retry control
- `async def retry_with_backoff(coro_func, *args, max_retries, base_delay, retryable_exceptions, operation_name, **kwargs) -> T`
- `@retry_decorator(max_retries, base_delay, retryable_exceptions, operation_name)`
- `async def handle_rate_limit(wait_seconds, operation_name, extra_buffer) -> None`

**timeout.py**
- `class TimeoutError(Exception)` — Operation timed out
- `class TimeoutContext` — Async context manager
- `async def with_timeout(coro, timeout, operation_name) -> T`
- `@timeout_decorator(timeout, operation_name)`
- `async def iter_with_timeout(async_iterator, timeout, operation_name)`
