# Message Listener System

## Overview

Real-time Telegram group message monitoring with Redis stream publishing for downstream processing.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Telegram Groups                           │
│                                                              │
│  Group 1 (-1001234567890)  Group 2 (-1009999999999)         │
└───────────────────────────────┬─────────────────────────────┘
                                │ Telethon Events
                                ▼
┌─────────────────────────────────────────────────────────────┐
│                   Listener (tg-bot listen)                   │
│                                                              │
│  - Filters by assigned groups                               │
│  - Extracts message metadata                                │
│  - Handles forum topics                                      │
│  - Emits heartbeats                                         │
└───────────────────────────────┬─────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│                         Redis                                │
│                                                              │
│  Stream: tg:listener:messages (max 1M messages)             │
│  Key: tg:listener:heartbeat:{listener_id} (TTL 30s)         │
└───────────────────────────────┬─────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│                    Consumers (tg-master)                     │
│                                                              │
│  XREAD GROUP analyzers consumer-1                           │
│  Process messages, update analytics, trigger responses      │
└─────────────────────────────────────────────────────────────┘
```

## Configuration

```bash
tg-bot listen \
  --groups -1001234567890,-1009999999999 \
  --listener-id my-listener-1 \
  --account-id 42 \
  --redis redis://localhost:6379 \
  --heartbeat-interval 10 \
  --debug
```

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--groups` | Yes | - | Comma-separated group IDs |
| `--listener-id` | No | Auto-generated | Unique listener identifier |
| `--account-id` | No | - | Database account ID |
| `--redis` | No | `redis://localhost:6379` | Redis URL |
| `--heartbeat-interval` | No | 10 | Heartbeat frequency (seconds) |
| `--debug` | No | False | Print messages to stdout |

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

### Example

```bash
# These all match group 1234567890:
--groups -1001234567890
--groups 1234567890
--groups -1001234567890,1234567890  # Both formats work
```

## Heartbeat System

### Purpose
- Monitor listener health
- Detect dead/stuck listeners
- Enable automatic restart by orchestrator

### Mechanism

```python
# Every heartbeat_interval seconds:
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

### Publishing

```python
async def publish(message: ChannelMessage) -> str:
    message_id = await redis.xadd(
        "tg:listener:messages",
        message.to_dict(),
        maxlen=1_000_000,
        approximate=True
    )
    return message_id
```

### Consuming

```python
# Consumer group read (tg-master side)
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

## Signal Handling

```python
# Graceful shutdown on SIGINT/SIGTERM
async def run_with_signal_handling():
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: stop())

    await start()
    await run_forever()
```

## Debug Mode

With `--debug`:
- Prints each message to stdout
- Format: `[{channel_id}] @{sender}: {text[:50]}...`
- Useful for testing without Redis consumers

## Integration with tg-master

### Starting Listener

```python
# tg-master spawns listener subprocess
subprocess.Popen([
    "tg-bot", "listen",
    "--groups", ",".join(map(str, group_ids)),
    "--listener-id", listener_id,
    "--account-id", str(account_id),
    "--redis", redis_url,
    "--heartbeat-interval", "10"
])
```

### Monitoring Health

```python
# Check all listeners
for listener_id in known_listeners:
    heartbeat = redis.get(f"tg:listener:heartbeat:{listener_id}")
    if not heartbeat:
        handle_dead_listener(listener_id)
```

### Consuming Messages

```python
# Message processing loop
while True:
    messages = await redis.xreadgroup(...)
    for msg in messages:
        await process_and_respond(msg)
```
