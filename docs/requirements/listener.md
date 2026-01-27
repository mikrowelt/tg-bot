# Message Listener System

## Overview

Real-time Telegram group message monitoring with Redis stream publishing for downstream processing.

> **Important:** As of January 2026, message listening is handled by **tg-session's internal listener**, not the standalone `tg-bot listen` command. This prevents session conflicts and account destruction.

## Architecture (Current - tg-session)

```
┌─────────────────────────────────────────────────────────────────┐
│                    Telegram Groups                               │
│                                                                  │
│  Group 1 (-1001234567890)  Group 2 (-1009999999999)             │
└───────────────────────────────┬─────────────────────────────────┘
                                │ Telethon Events
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                   tg-session (Port 8200)                         │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              ListenerManager (internal)                   │   │
│  │                                                          │   │
│  │  - Manages listener lifecycle via API                    │   │
│  │  - Shares connection pool with operations                │   │
│  │  - Pause/resume for command execution                    │   │
│  │  - NO session conflicts (single owner)                   │   │
│  └──────────────────────────────────────────────────────────┘   │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Redis                                    │
│                                                                  │
│  Stream: tg:listener:messages (max 1M messages)                 │
│  Key: tg:listener:heartbeat:{listener_id} (TTL 30s)             │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Consumers (tg-master)                         │
│                                                                  │
│  XREAD GROUP analyzers consumer-1                               │
│  Process messages, update analytics, trigger responses          │
└─────────────────────────────────────────────────────────────────┘
```

## Starting Listeners (via tg-session API)

```python
# tg-master starts listener via tg-session
async with httpx.AsyncClient() as client:
    response = await client.post(
        f"{TG_SESSION_URL}/accounts/{account_id}/listen/start",
        json={
            "groups": [-1001234567890, -1009999999999],
            "listener_id": "listener-1"
        }
    )
```

### API Endpoints (tg-session)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/accounts/{id}/listen/start` | Start listener for account |
| POST | `/accounts/{id}/listen/stop` | Stop listener |
| PUT | `/accounts/{id}/listen/groups` | Update monitored groups |
| GET | `/listeners` | List all active listeners |

## Message Format

### ChannelMessage

```python
@dataclass
class ChannelMessage:
    channel_id: int              # Group/channel ID
    message_id: int              # Message ID
    text: str                    # Message text
    sender_id: int | None        # Sender user ID
    sender_username: str | None  # Sender username
    message_date: str            # ISO format timestamp
    has_media: bool              # True if has media attachment
    media_type: str | None       # "photo", "video", "document", etc
    reply_to_msg_id: int | None  # If replying to another message
    discussion_group_id: int | None  # Linked discussion group
    listener_id: str | None      # This listener's ID
    topic_id: int | None         # Forum topic ID
    is_forum_topic: bool         # True if in forum group
    chat_type: str | None        # "channel", "supergroup", "group"
```

### Redis Stream Entry

```json
{
  "channel_id": "-1001234567890",
  "message_id": "12345",
  "text": "Hello world",
  "sender_id": "987654321",
  "sender_username": "john_doe",
  "message_date": "2024-01-15T12:34:56Z",
  "has_media": "false",
  "media_type": "null",
  "reply_to_msg_id": "null",
  "discussion_group_id": "null",
  "listener_id": "my-listener-1",
  "topic_id": "null",
  "is_forum_topic": "false",
  "chat_type": "supergroup"
}
```

## Group Filtering

### ID Handling

Telegram uses negative IDs for supergroups/channels:
- Supergroup: `-1001234567890`
- Channel: `-1001234567890`
- Regular group: positive ID

**Filtering Logic:**
```python
if assigned_groups:
    chat_id = event.chat_id        # Negative for supergroups
    raw_id = abs(chat_id) % 10**10  # Positive ID without prefix

    if chat_id not in assigned_groups and raw_id not in assigned_groups:
        return  # Skip this group
```

## Heartbeat System

### Purpose
- Monitor listener health
- Detect dead/stuck listeners
- Enable automatic restart by orchestrator

### Mechanism

```python
# tg-session emits heartbeat every 10 seconds:
redis.setex(
    f"tg:listener:heartbeat:{listener_id}",
    30,  # TTL
    json.dumps({
        "account_id": account_id,
        "timestamp": datetime.utcnow().isoformat(),
        "groups": assigned_group_ids
    })
)
```

### Monitoring (tg-master)

```python
# Check listener health
heartbeat = redis.get(f"tg:listener:heartbeat:{listener_id}")
if not heartbeat:
    # Listener is dead (no heartbeat for 30s)
    restart_listener(listener_id)
```

## Redis Stream Details

### Stream Configuration

| Setting | Value |
|---------|-------|
| Stream key | `tg:listener:messages` |
| Max length | 1,000,000 entries |
| Consumer group | `analyzers` |
| Trim strategy | `MAXLEN ~` (approximate) |

### Consuming (tg-master)

```python
# Consumer group read
messages = await redis.xreadgroup(
    "analyzers",
    "consumer-1",
    {"tg:listener:messages": ">"},
    count=100,
    block=5000
)

for stream, entries in messages:
    for entry_id, fields in entries:
        process_message(fields)
        await redis.xack("tg:listener:messages", "analyzers", entry_id)
```

## Forum Topic Support

### Detection

```python
# Check if group has forum mode
if getattr(chat, 'forum', False):
    is_forum_topic = True
    topic_id = message.reply_to.reply_to_top_id  # Topic thread ID
```

### Message Context

Forum messages include:
- `topic_id`: The forum topic ID
- `is_forum_topic`: True
- `chat_type`: "supergroup"

## Error Handling

| Error | Behavior |
|-------|----------|
| Telegram disconnect | Automatic reconnect by Telethon |
| Redis connection lost | Reconnect with backoff |
| Message processing error | Log and continue |
| FloodWait | Log and wait |

---

## Legacy: tg-bot listen Command (DEPRECATED)

> **Warning:** The standalone `tg-bot listen` command is **DEPRECATED** as of January 2026. Using it directly risks session destruction due to concurrent access conflicts.

The command still exists for backwards compatibility but should not be used:

```bash
# DEPRECATED - Do not use directly
tg-bot listen \
  --groups -1001234567890,-1009999999999 \
  --listener-id my-listener-1 \
  --account-id 42 \
  --redis redis://localhost:6379
```

**Why deprecated:**
- Running `tg-bot listen` while tg-session manages the same account causes `AuthKeyDuplicatedError`
- Session files are permanently destroyed
- No recovery possible - must create new Telegram account

**Migration:**
All listener management now goes through tg-session API. See [tg-session documentation](../../../tg-session/docs/INDEX.md).

---

## See Also

- [tg-session Documentation](../../../tg-session/docs/INDEX.md) - Session gateway with internal listener
- [Worker Dispatcher](worker-dispatcher.md) - Task queue processing
