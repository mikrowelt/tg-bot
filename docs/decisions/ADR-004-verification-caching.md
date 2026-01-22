# ADR-004: Verification Pattern Caching

## Status
Accepted

## Context

AI verification using Claude API is:
- **Expensive** — API calls cost money
- **Slow** — Network latency adds 2-5 seconds
- **Repetitive** — Same bots ask same questions

Many verification bots use identical patterns:
- Same message text (with dynamic usernames)
- Same button layouts
- Same expected responses

## Decision

Implement **fingerprint-based caching** for verification patterns:

### Fingerprinting

Normalize verification messages to create stable fingerprints:

```python
def _normalize_text(self, text, our_username, our_first_name):
    normalized = text.lower().strip()
    normalized = normalized.replace(our_username, "{user}")
    normalized = normalized.replace(our_first_name, "{name}")
    normalized = re.sub(r'\d+', '{num}', normalized)  # Numbers
    normalized = emoji_pattern.sub('{emoji}', normalized)
    return normalized

def _create_fingerprint(self, bot, text, buttons):
    data = {
        "bot": bot.lower(),
        "pattern": normalize(text),
        "buttons": sorted([normalize(b) for b in buttons])
    }
    return sha256(json.dumps(data)).hexdigest()[:16]
```

### Cache Entry

```python
@dataclass
class CachedAction:
    action_type: str        # "click_button", "send_message"
    action_data: dict       # Action parameters
    success_count: int = 0
    fail_count: int = 0

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.fail_count
        return self.success_count / total if total > 0 else 0.0
```

### Cache Hit Criteria

Only use cached action if `success_rate >= 0.5` (50%).

### Math Problem Exception

**Never cache math problem answers** — numbers change each time.

```python
use_cache = cached_action and not (
    cached_action.action_type == "send_message" and
    self._looks_like_math(message.text)
)
```

## Consequences

### Benefits
- **Cost reduction** — Fewer AI API calls
- **Speed** — Cache hit skips AI latency
- **Learning** — Success rates improve recommendations
- **Consistency** — Same bot gets same response

### Drawbacks
- **Cache staleness** — Bot might change verification
- **Memory growth** — Unbounded cache size
- **False positives** — Similar but different patterns

### Mitigation
- Success rate threshold prevents bad cache entries
- Math problems explicitly excluded
- Thread-safe with asyncio.Lock
- Could add LRU eviction in future
