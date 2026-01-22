# Message Sending

## Overview

Send messages to users, groups, channels with support for replies, comments, reactions, and forum topics.

## Operations

### Send Message

Send to any chat (user, group, channel, supergroup).

```bash
tg-bot send-message <target> <text> [--reply-to ID]
```

**Examples:**
```bash
# Direct message
tg-bot send-message @username "Hello!"

# Reply to message
tg-bot send-message -1001234567890 "Thanks!" --reply-to 123

# Forum topic
tg-bot send-message -1001234567890 "Topic post" --topic-id 456
```

### Send Comment

Comment on a broadcast channel post.

```bash
tg-bot send-message <channel> <text> --comment-to <post_id>
```

**Requirements:**
- Target must be a broadcast channel
- Channel must have comments enabled (discussion group)

**Flow:**
1. Verify target is broadcast channel
2. Get linked discussion group
3. Send via `comment_to` parameter
4. Optionally check for verification

### Send Reaction

React to a message with emoji.

```python
result = await bot.send_reaction(channel, message_id, emoji="👍")
```

**Supported emojis:** Standard Telegram reaction set

## SendResult

All operations return `SendResult`:

```python
@dataclass
class SendResult:
    ok: bool                        # Success?
    message_id: int | None          # Sent message ID
    error: str | None               # Error code
    retryable: bool = True          # Can retry?
    wait_seconds: int | None = None # Wait time for rate limit
```

### Error Codes

| Code | Cause | Retryable |
|------|-------|-----------|
| `banned` | No write permission | No |
| `channel_private` | Channel deleted | No |
| `chat_restricted` | Chat restricted | No |
| `forbidden` | Generic forbidden | No |
| `flood_wait` | Rate limited | Yes |
| `slow_mode` | Slow mode active | Yes |

## Forum Topics

Supergroups can enable "Topics" (forum mode).

### Listing Topics

```python
topics = await bot.get_forum_topics(supergroup)
# Returns list with topic IDs and titles
```

### Sending to Topic

```python
result = await bot.send_message(
    supergroup,
    "Message text",
    topic_id=123  # Send to specific topic
)
```

**Note:** The General topic typically has ID=1.

### Topic Messages

```python
messages = await bot.get_recent_messages_in_topic(supergroup, topic_id=123)
```

## Verification After Send

For first message in a chat, bots may require verification.

```python
result = await bot.send_message(
    target,
    "Hello!",
    check_verification=True,      # Check for verification
    verification_wait_seconds=3   # Wait before checking
)
```

**Flow:**
1. Send message
2. Wait specified seconds
3. Check for bot reply with verification
4. Handle verification automatically

## Rate Limiting

### Telegram Limits

- **Messages per hour:** ~100+ (varies)
- **Slow mode:** Per-chat cooldown (1s to 1h)
- **Flood wait:** Global rate limit

### Anti-Detection

- 1-3 second delay before sending
- 2-4 second delay after sending
- Human-like typing simulation (future)

### Error Recovery

```python
result = await bot.send_message(target, text)

if not result.ok:
    if result.retryable:
        if result.wait_seconds:
            await asyncio.sleep(result.wait_seconds + 5)
        # Retry...
    else:
        # Permanent failure, don't retry
        handle_permanent_error(result.error)
```

## Comments vs Direct Messages

| Type | Use Case | Telethon Parameter |
|------|----------|-------------------|
| Direct | Messages to users/groups | `send_message(target, text)` |
| Reply | Reply to specific message | `send_message(target, text, reply_to=id)` |
| Comment | Comment on channel post | `send_message(channel, text, comment_to=post_id)` |
| Topic | Message in forum topic | `send_message(group, text, reply_to=topic_id)` |

## Implementation Details

### Comment Routing

When `comment_to` is set:
1. Check target is broadcast channel
2. Get channel's linked discussion group
3. Send to discussion group with `comment_to`
4. Telethon routes to correct thread

### Reply Threading

When `reply_to` is set with `comment_to`:
1. Get discussion group ID
2. Send directly to discussion group
3. Use `reply_to` for threading within discussion
