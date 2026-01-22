# Profile Management

## Overview

Full CRUD operations for Telegram profile: name, bio, username, and photos.

## Operations

### Get Profile

Retrieve current profile information.

```bash
tg-bot get-profile [--include-photo]
```

**Returns:**
- `user_id` — Telegram user ID
- `username` — Current username (or null)
- `first_name` — First name
- `last_name` — Last name (or null)
- `bio` — About text (or null)
- `photo` — Base64 profile photo (if `--include-photo`)

### Change Profile

Update profile fields. All arguments optional — only provided fields are updated.

```bash
tg-bot change-profile \
  --first-name "John" \
  --last-name "Doe" \
  --about "Hello world" \
  --username "johndoe" \
  --photo /path/to/photo.jpg
```

**Behavior:**
- Skips unchanged fields
- Adds human-like delay (3-7 seconds)
- Username auto-retries with numbers if taken

### Profile Health Check

Validate profile matches expected values.

```bash
tg-bot profile-health-check \
  --expected-first-name "John" \
  --expected-last-name "Doe" \
  --expected-username "johndoe" \
  --expected-about "Hello world"
```

**Returns:**
```json
{
  "matches": true,
  "mismatches": []
}
```

Or if mismatch:
```json
{
  "matches": false,
  "mismatches": [
    {"field": "username", "expected": "johndoe", "actual": "john_doe_123"}
  ]
}
```

## Username Handling

### Auto-Retry Logic

When setting username, if taken:
1. Try original: `johndoe`
2. Try with numbers: `johndoe1`, `johndoe2`, ...
3. Up to 10 attempts

### Validation

- 5-32 characters
- Letters, numbers, underscores
- Must start with letter
- Case-insensitive (lowercase stored)

### Errors

| Error | Cause |
|-------|-------|
| `UsernameOccupiedError` | Username taken (auto-retry) |
| `UsernameInvalidError` | Invalid format |
| `FloodWaitError` | Rate limited |

## Photo Management

### Upload Photo

```python
await bot.change_profile(photo="/path/to/photo.jpg")
```

**Supported formats:** JPEG, PNG
**Max size:** 5MB

### Delete All Photos

```python
await bot.delete_all_profile_photos()
```

Removes entire photo history.

### Get Photo History

```python
photos = await bot.get_profile_photos()
# Returns list of photo file references
```

## Rate Limiting

Profile changes are rate-limited by Telegram:
- Name/bio: ~1 change per few hours
- Username: More restricted
- Photo: ~1 change per day

**Anti-detection:**
- 3-7 second delay between operations
- Human-like timing for multi-field updates
