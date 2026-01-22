# CLI Commands

## Overview

tg-bot provides 11 user-facing commands for Telegram automation, plus 2 internal commands for the worker system.

## Command Reference

### Profile Commands

#### `health-check`
Verify client connectivity and account status.

```bash
tg-bot health-check
```

**Output:**
```json
{
  "ok": true,
  "connected": true,
  "authorized": true,
  "user_id": 123456789,
  "username": "myusername",
  "restricted": false
}
```

**Exit Codes:**
- `0` — Healthy
- `1` — Connection/auth error or account restricted

---

#### `get-profile`
Retrieve current profile information.

```bash
tg-bot get-profile [--include-photo]
```

| Argument | Description |
|----------|-------------|
| `--include-photo` | Include base64-encoded profile photo |

**Output:**
```json
{
  "user_id": 123456789,
  "username": "myusername",
  "first_name": "John",
  "last_name": "Doe",
  "bio": "Hello world",
  "photo": "base64..."  // if --include-photo
}
```

---

#### `profile-health-check`
Validate profile matches expected values.

```bash
tg-bot profile-health-check \
  --expected-first-name "John" \
  --expected-last-name "Doe" \
  --expected-username "johndoe" \
  --expected-about "My bio"
```

| Argument | Description |
|----------|-------------|
| `--expected-first-name` | Expected first name |
| `--expected-last-name` | Expected last name |
| `--expected-username` | Expected username |
| `--expected-about` | Expected bio |

**Output:**
```json
{
  "matches": true,
  "mismatches": []
}
```

---

#### `change-profile`
Update profile name, bio, username, or photo.

```bash
tg-bot change-profile \
  --first-name "John" \
  --last-name "Doe" \
  --about "New bio" \
  --username "newusername" \
  --photo /path/to/photo.jpg
```

| Argument | Description |
|----------|-------------|
| `--first-name` | New first name |
| `--last-name` | New last name |
| `--about` | New bio |
| `--username` | New username (retries with numbers if taken) |
| `--photo` | Path to new profile photo |

All arguments are optional — only provided fields are updated.

---

### Channel Commands

#### `join-channel`
Join a channel and optionally pass bot verification.

```bash
tg-bot join-channel <channel> [--skip-verification]
```

| Argument | Description |
|----------|-------------|
| `<channel>` | Channel link or @username |
| `--skip-verification` | Don't run verification after joining |

**Supported formats:**
- `https://t.me/channelname`
- `https://t.me/+invitehash`
- `@channelname`

**Output:**
```json
{
  "channel_id": -1001234567890
}
```

---

#### `check-ban`
Check if account is banned from a channel.

```bash
tg-bot check-ban <target> [--test-message]
```

| Argument | Description |
|----------|-------------|
| `<target>` | Channel ID, link, or @username |
| `--test-message` | Attempt to send a test message (more reliable) |

**Output:**
```json
{
  "is_member": true,
  "is_banned": false,
  "can_write": true,
  "target_type": "supergroup"
}
```

---

#### `check-all-bans`
Batch check bans across multiple channels.

```bash
tg-bot check-all-bans <channels>... [--no-test-message]
```

| Argument | Description |
|----------|-------------|
| `<channels>` | Space-separated list of channels |
| `--no-test-message` | Skip test message sending |

**Output:**
```json
{
  "results": [
    {"channel": "@chan1", "is_banned": false},
    {"channel": "@chan2", "is_banned": true}
  ]
}
```

---

#### `chat-info`
Get channel/group details and forum topics.

```bash
tg-bot chat-info <target> [--topics] [--posts N] [--json]
```

| Argument | Description |
|----------|-------------|
| `<target>` | Channel/group ID or @username |
| `--topics` | Include forum topics (supergroups only) |
| `--posts N` | Number of recent posts to fetch |
| `--json` | Output as JSON |

---

### Message Commands

#### `send-message`
Send a message, reply, or comment.

```bash
tg-bot send-message <target> <text> [--reply-to ID] [--comment-to ID]
```

| Argument | Description |
|----------|-------------|
| `<target>` | Chat/channel ID or @username |
| `<text>` | Message text |
| `--reply-to ID` | Message ID to reply to |
| `--comment-to ID` | Post ID to comment on (broadcast channels) |

**Output:**
```json
{
  "ok": true,
  "message_id": 12345
}
```

---

### Worker Commands

#### `worker`
Run the task dispatcher (watches Redis queues).

```bash
tg-bot worker --profiles <profiles> [--redis URL] [--result-ttl N]
```

| Argument | Description |
|----------|-------------|
| `--profiles` | Comma-separated profile names |
| `--all` | Watch all profiles in BASE_DIR |
| `--redis` | Redis URL (default: `redis://localhost:6379`) |
| `--result-ttl` | Result TTL in seconds (default: 300) |

---

#### `run-task` (internal)
Execute a single task from the queue.

```bash
tg-bot run-task --profile <name> [--redis URL] [--result-ttl N] [--timeout N]
```

Spawned by the dispatcher, not for direct use.

---

#### `listen`
Monitor group messages and publish to Redis stream.

```bash
tg-bot listen \
  --groups <ids> \
  [--listener-id ID] \
  [--account-id ID] \
  [--redis URL] \
  [--heartbeat-interval N] \
  [--debug]
```

| Argument | Description |
|----------|-------------|
| `--groups` | Comma-separated group IDs (negative for supergroups) |
| `--listener-id` | Unique listener identifier |
| `--account-id` | Database account ID for heartbeats |
| `--redis` | Redis URL |
| `--heartbeat-interval` | Heartbeat frequency in seconds |
| `--debug` | Print messages to stdout |

## Global Options

All commands support:

| Option | Description |
|--------|-------------|
| `--profile NAME` | Profile name (overrides PROFILE_NAME env) |
| `--log-level LEVEL` | DEBUG, INFO, WARNING, ERROR |
| `--log-format FORMAT` | simple, detailed, json |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error (config, auth, operation failure) |
| 2 | No task in queue (run-task only) |
