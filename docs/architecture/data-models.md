# Data Models

## Configuration Models

### Config (`utils/config.py`)

Main configuration loaded from profile JSON and environment.

```python
class Config(BaseModel):
    # Paths
    profile_path: Path          # Path to profile.json
    session_path: Path          # Path to session file (no extension)

    # Optional services
    captcha_api_key: str | None # 2Captcha API key
    proxy: ProxyConfig | None   # Proxy configuration

    # Telegram credentials (from profile.json)
    app_id: int                 # Telegram app ID
    app_hash: str               # Telegram app hash
    phone: str                  # Phone number (digits only)
    device: str = "Unknown"     # Device model for user agent
    sdk: str = "Windows 10"     # SDK version
    app_version: str = "1.0.0"  # App version
    lang_pack: str = "en"       # Language pack
    two_fa: str | None = None   # 2FA password
```

**Loading:**
```python
config = Config.load("profile_name")
# Loads from {BASE_DIR}/{profile_name}.json
# Session file at {BASE_DIR}/{profile_name}.session
```

### ProxyConfig (`utils/config.py`)

```python
class ProxyConfig(BaseModel):
    type: int           # socks.SOCKS5, socks.SOCKS4, socks.HTTP
    host: str           # Proxy host
    port: int           # 1-65535
    username: str | None
    password: str | None

    def to_tuple(self) -> tuple:
        # Returns format expected by Telethon
        if self.username and self.password:
            return (self.type, self.host, self.port, True, self.username, self.password)
        return (self.type, self.host, self.port)
```

## Operation Results

### SendResult (`client_messages.py`)

Result of message sending operations.

```python
@dataclass
class SendResult:
    ok: bool                        # True if sent successfully
    message_id: int | None = None   # ID of sent message
    error: str | None = None        # Error code if failed
    retryable: bool = True          # True if error is temporary
    wait_seconds: int | None = None # FloodWait seconds
```

**Error Codes:**
| Code | Cause | Retryable |
|------|-------|-----------|
| `banned` | ChatWriteForbidden, UserBannedInChannel | No |
| `channel_private` | ChannelPrivateError | No |
| `chat_restricted` | ChatRestrictedError | No |
| `forbidden` | ForbiddenError | No |
| `flood_wait` | FloodWaitError | Yes |
| `slow_mode` | SlowModeWaitError | Yes |

### VerificationResult (`verification/ai_agent.py`)

Result of AI verification attempt.

```python
@dataclass
class VerificationResult:
    success: bool                   # True if completed
    action_taken: str | None = None # "click_button", "send_message", etc
    error: str | None = None        # Error message
    cached: bool = False            # True if used cached action
    details: dict = field(default_factory=dict)
```

## Task Queue Models

### Task (`worker/task.py`)

Task definition for queue.

```python
@dataclass
class Task:
    task_id: str        # Unique identifier (UUID)
    command: Command    # Enum value
    args: dict[str, Any]
```

### Command (`worker/task.py`)

```python
class Command(Enum):
    JOIN_CHANNEL = "join_channel"
    SEND_MESSAGE = "send_message"
    CHANGE_PROFILE = "change_profile"
    GET_PROFILE = "get_profile"
    PROFILE_HEALTH_CHECK = "profile_health_check"
```

### TaskResult (`worker/task.py`)

```python
@dataclass
class TaskResult:
    task_id: str
    status: TaskStatus          # SUCCESS or ERROR
    result: dict | None = None  # Command output
    error: str | None = None    # Error message
    error_type: str | None = None  # Exception class name

class TaskStatus(Enum):
    SUCCESS = "success"
    ERROR = "error"
```

## Listener Models

### ChannelMessage (`listener/listener.py`)

Message captured from Telegram group.

```python
@dataclass
class ChannelMessage:
    channel_id: int                 # Group/channel ID
    message_id: int                 # Message ID
    text: str                       # Message text
    sender_id: int | None           # Sender user ID
    sender_username: str | None     # Sender username
    message_date: str               # ISO format
    has_media: bool                 # Has attachment
    media_type: str | None          # "photo", "video", etc
    reply_to_msg_id: int | None     # Reply target
    discussion_group_id: int | None # Linked discussion
    listener_id: str | None         # This listener's ID
    topic_id: int | None            # Forum topic ID
    is_forum_topic: bool            # In forum group
    chat_type: str | None           # "channel"/"supergroup"/"group"
```

## Verification Cache Models

### CachedAction (`verification/ai_agent.py`)

```python
@dataclass
class CachedAction:
    action_type: str            # "click_button", "send_message"
    action_data: dict           # Action parameters
    success_count: int = 0      # Successful uses
    fail_count: int = 0         # Failed uses
    last_used: datetime = field(default_factory=datetime.utcnow)

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.fail_count
        return self.success_count / total if total > 0 else 0.0
```

## Profile JSON Schema

**File:** `{profile_name}.json`

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

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `app_id` | int | Yes | From my.telegram.org |
| `app_hash` | string | Yes | From my.telegram.org |
| `phone` | string | Yes | Digits only, no + |
| `device` | string | No | Device model |
| `sdk` | string | No | SDK version |
| `app_version` | string | No | App version |
| `lang_pack` | string | No | Language code |
| `two_fa` / `twoFA` | string | No | 2FA password |

## Redis Data Structures

### Task Queue

**Key:** `tasks:{profile_name}`
**Type:** List
**Value:** JSON-serialized Task

```json
{
  "task_id": "abc123-def456",
  "command": "join_channel",
  "args": {
    "channel": "https://t.me/channel",
    "skip_verification": false
  }
}
```

### Task Result

**Key:** `result:{task_id}`
**Type:** String
**TTL:** 300 seconds
**Value:** JSON-serialized TaskResult

```json
{
  "task_id": "abc123-def456",
  "status": "success",
  "result": {"channel_id": -1001234567890},
  "error": null,
  "error_type": null
}
```

### Message Stream

**Key:** `tg:listener:messages`
**Type:** Stream
**Max Length:** 1,000,000

### Heartbeat

**Key:** `tg:listener:heartbeat:{listener_id}`
**Type:** String
**TTL:** 30 seconds

```json
{
  "account_id": 42,
  "timestamp": "2024-01-15T12:34:56Z",
  "groups": [-1001234567890]
}
```
