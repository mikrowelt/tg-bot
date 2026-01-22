# Bot Verification System

## Overview

Automatic handling of Telegram bot verification after joining channels. Supports multiple verification methods with intelligent fallback.

## Verification Methods

### 1. Math Solver

**Capability:** Extracts and solves simple arithmetic problems.

**Patterns Detected:**
- `5 + 3 = ?`
- `What is 10 - 2?`
- `Solve: 4 * 7`
- `Calculate 20 / 4`

**Operators:**
- Addition: `+`
- Subtraction: `-`
- Multiplication: `*`, `×`, `x`
- Division: `/`, `÷`

**Behavior:**
- Returns integer result as string
- Handles negative results
- Skips division by zero

---

### 2. Button Verification

**Capability:** Clicks inline keyboard buttons.

**Button Types:**
| Type | Action |
|------|--------|
| `KeyboardButtonCallback` | Clicks with callback data |
| `KeyboardButtonUrl` | Triggers PM verification |

**Priority:**
1. First detects math problems in message text
2. Falls back to callback button clicking
3. Falls back to URL button (PM verification)

---

### 3. Image Captcha (2Captcha)

**Capability:** Solves image-based captchas via 2Captcha API.

**Requirements:**
- `CAPTCHA_API_KEY` environment variable
- Active 2Captcha account with balance

**Flow:**
1. Download captcha image from bot message
2. Base64-encode image
3. Submit to 2Captcha API
4. Poll for solution (up to 60 seconds)
5. Reply with solution text

**Timeout:** 120 seconds total

---

### 4. PM Verification

**Capability:** Handles "click to verify in PM" flows.

**Flow:**
1. Detect URL button pointing to bot
2. Send `/start` to bot in private message
3. Wait for response (4-7 seconds)
4. Click first button if present

---

### 5. AI Verification Agent

**Capability:** Claude-powered intelligent verification.

**Requirements:**
- `ANTHROPIC_API_KEY` environment variable

**Features:**
- Analyzes message context with AI
- Determines appropriate action
- Caches successful patterns
- Handles complex multi-step verification

**Cache System:**
- Fingerprints based on: bot username, message text, button texts
- Normalizes dynamic values (usernames, numbers)
- Uses success rate ≥50% for cache hits
- Thread-safe with asyncio.Lock

## Verification Flow

### On Channel Join

```
join_channel(verify=True)
    │
    ├── AI Verification Available?
    │   ├── Yes → check_and_handle_verification(channel_id)
    │   │         check_and_handle_verification(discussion_group_id)
    │   │         check_post_comments_verification()
    │   │         check_dm_verification()
    │   │
    │   └── No → ButtonVerification.verify(channel_id)
    │            ButtonVerification.verify(discussion_group_id)
    │
    └── Wait for permissions (2-5 seconds)
```

### Button Verification Priority

```
ButtonVerification.verify(channel_id)
    │
    ├── 1. Scan recent bot messages (limit=5)
    │
    ├── 2. Check for math problem
    │   └── If found → solve and reply → return
    │
    ├── 3. Check for image captcha
    │   └── If found → solve with 2Captcha → reply → return
    │
    ├── 4. Check for callback buttons
    │   └── If found → click first button → return
    │
    └── 5. Check for URL buttons (PM verification)
        └── If found → trigger PM flow → return
```

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `CAPTCHA_API_KEY` | For captcha | 2Captcha API key |
| `ANTHROPIC_API_KEY` | For AI | Anthropic Claude API key |

### Timing Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `WAIT_VERIFICATION` | 3-5s | Between verification attempts |
| `WAIT_HUMAN` | 3-6s | Simulating human reading |
| `DELAY_CAPTCHA_POLL` | 5s | Captcha solution polling |
| `DELAY_CAPTCHA_INITIAL` | 10s | Initial captcha wait |
| `TIMEOUT_CAPTCHA` | 120s | Max captcha solving time |

## Error Handling

| Error | Cause | Recovery |
|-------|-------|----------|
| `VerificationError` | Verification failed | Logged, join still succeeds |
| `CaptchaError` | 2Captcha API failure | Falls back to next method |
| `FloodWaitError` | Rate limited | Raises with wait time |
| `PMVerificationError` | PM flow failed | Falls back to next method |

## Rate Limiting

**Single Action Rule:** Only ONE verification action is performed per call to avoid account freezes.

**FloodWait Handling:**
- Catches `FloodWaitError`
- Logs wait time
- Raises `VerificationError` with wait seconds
- Caller decides whether to retry

## AI Verification Details

### Cache Fingerprinting

```python
# Normalized fingerprint components:
{
    "bot": "verify_bot",           # Lowercase bot username
    "pattern": "click {num} to verify {user}",  # Normalized text
    "buttons": ["verify", "cancel"]  # Sorted button texts
}
```

**Normalization:**
- Username → `{user}`
- Numbers → `{num}`
- Emojis → `{emoji}`
- Whitespace → single space

### Verification Result

```python
@dataclass
class VerificationResult:
    success: bool                    # True if action completed
    action_taken: str | None         # "click_button", "send_message", etc
    error: str | None                # Error message if failed
    cached: bool = False             # True if used cached action
    details: dict = {}               # Additional context
```

### Contexts

| Context | Location | Trigger |
|---------|----------|---------|
| `after_join` | Channel | After joining channel |
| `after_join_discussion` | Discussion group | After joining discussion |
| `post_comment_verification` | Post comments | Bot in post thread |
| `DM verification` | Private message | Bot DMs after join |
