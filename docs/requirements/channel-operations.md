# Channel Operations

## Overview

Join/leave channels, check membership, detect bans, and query channel information.

## Operations

### Join Channel

Join a channel and optionally pass bot verification.

```bash
tg-bot join-channel <channel> [--skip-verification]
```

**Supported formats:**
- Public: `https://t.me/channelname` or `@channelname`
- Private: `https://t.me/+invitehash`

**Flow:**
1. Resolve channel entity
2. Send join request
3. Auto-join linked discussion group (if exists)
4. Run verification (unless `--skip-verification`)
5. Return channel ID

**Verification:**
- AI verification (if `ANTHROPIC_API_KEY` set)
- Button verification (fallback)
- Checks: channel, discussion group, post comments, DMs

### Leave Channel

```python
result = await bot.leave_channel(channel)
# {"success": True, "channel_id": -1001234567890}
```

### Check Membership

```python
result = await bot.check_channel_membership(target)
# {
#   "is_member": True,
#   "target_type": "supergroup",
#   "channel_id": -1001234567890,
#   "error": None
# }
```

**Handles:**
- Public channels by username
- Private channels via invite link
- Dialog cache refresh for stale lookups

### Check Ban

```bash
tg-bot check-ban <target> [--test-message]
```

**Detection methods:**
1. Membership check
2. Test message (if `--test-message`)

**Returns:**
```json
{
  "is_member": true,
  "is_banned": false,
  "can_write": true,
  "target_type": "supergroup"
}
```

### Batch Ban Check

```bash
tg-bot check-all-bans @chan1 @chan2 @chan3 [--no-test-message]
```

Checks multiple channels sequentially with delays.

## Channel Information

### Get Channel Info

```bash
tg-bot chat-info <target> [--posts N] [--topics] [--json]
```

**Returns:**
- `id` — Channel ID
- `title` — Channel name
- `username` — Public username
- `description` — About text
- `member_count` — Subscriber count
- `type` — "channel", "supergroup", "group"
- `is_forum` — Forum mode enabled
- `comments_enabled` — Has discussion group
- `recent_posts` — Latest posts (if requested)

### Get Available Reactions

Query which reactions are allowed on a channel/group.

```python
reactions = await bot.get_available_reactions(channel)
```

**Return values:**
- `None` — All emoji reactions are allowed (`ChatReactionsAll`)
- `[]` — No reactions allowed (`ChatReactionsNone`)
- `["👍", "❤️", ...]` — Only these specific emoji allowed (`ChatReactionsSome`)

**Implementation:**
- Uses `GetFullChannelRequest` to get `full_chat.available_reactions`
- Handles three Telegram reaction types:
  - `ChatReactionsNone` → return `[]`
  - `ChatReactionsAll` → return `None`
  - `ChatReactionsSome` → extract `emoticon` from each `ReactionEmoji` in list

**Use case:**
Before sending a reaction to a message, check which reactions are allowed to avoid "Invalid reaction provided" errors.

**Classes:**
- `InfoMixin.get_available_reactions(channel: int | str) -> list[str] | None`

**Telethon types used:**
- `telethon.tl.types.ChatReactionsNone`
- `telethon.tl.types.ChatReactionsAll`
- `telethon.tl.types.ChatReactionsSome`
- `telethon.tl.types.ReactionEmoji`

### Get Forum Topics

For supergroups with forum mode:

```python
topics = await bot.get_forum_topics(channel)
# [
#   {"id": 1, "title": "General", "is_general": True},
#   {"id": 123, "title": "Announcements", "is_closed": False}
# ]
```

## Error Handling

| Error | Cause | Retryable |
|-------|-------|-----------|
| `JoinChannelError` | Join failed | Depends |
| `FloodWaitError` | Rate limited | Yes |
| `UserAlreadyParticipantError` | Already member | N/A (success) |
| `ChannelPrivateError` | Channel deleted | No |
| `InviteHashExpiredError` | Invite expired | No |

## Rate Limiting

- **Join cooldown:** 30 minutes per account per proxy
- **Typical join rate:** 5-10 channels per hour
- **Anti-detection:** 2-5 second delays

## Linked Discussion Groups

Broadcast channels can have linked discussion groups for comments.

**Auto-join behavior:**
1. After joining channel, get full channel info
2. Check for `linked_chat_id`
3. If exists, auto-join discussion group
4. Run verification on both

This enables commenting on channel posts.
