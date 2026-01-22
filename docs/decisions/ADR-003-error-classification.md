# ADR-003: Error Classification Strategy

## Status
Accepted

## Context

Telegram operations can fail for various reasons:
- **Temporary** — Rate limits, network issues
- **Permanent** — Banned, channel deleted, no permissions

Upstream systems (tg-master) need to know whether to:
- Retry the operation later
- Mark the task as failed
- Mark the account as problematic

Simply raising exceptions loses important context.

## Decision

Classify errors in `SendResult` with structured fields:

```python
@dataclass
class SendResult:
    ok: bool                        # Success/failure
    message_id: int | None          # If successful
    error: str | None               # Error code
    retryable: bool = True          # Can retry?
    wait_seconds: int | None = None # How long to wait
```

**Error classification:**

| Error Code | Retryable | Cause |
|------------|-----------|-------|
| `banned` | No | Account banned from target |
| `channel_private` | No | Channel deleted/private |
| `forbidden` | No | No write permission |
| `flood_wait` | Yes | Rate limited (wait N seconds) |
| `slow_mode` | Yes | Chat slow mode active |

**Implementation:**
```python
def _handle_send_error(self, error: Exception) -> SendResult:
    if isinstance(error, ChatWriteForbiddenError):
        return SendResult(ok=False, error="banned", retryable=False)
    if isinstance(error, FloodWaitError):
        return SendResult(ok=False, error="flood_wait",
                         retryable=True, wait_seconds=error.seconds)
    # ...
```

## Consequences

### Benefits
- **Smart retries** — Only retry retryable errors
- **Clear semantics** — Upstream knows exactly what happened
- **Account health** — Track accounts with too many permanent errors
- **Rate limit handling** — Know exactly how long to wait

### Drawbacks
- **Boilerplate** — Must map each Telethon error
- **Maintenance** — New errors need classification
- **Two systems** — Both exceptions and SendResult used

### Mitigation
- Centralize error mapping in `_handle_send_error()`
- Use exceptions for truly exceptional cases (config errors)
- Use SendResult for expected operation outcomes
