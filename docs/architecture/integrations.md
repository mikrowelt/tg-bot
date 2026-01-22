# External Integrations

## Telegram (Telethon)

### Connection

```python
from telethon import TelegramClient

client = TelegramClient(
    session_path,           # SQLite session file
    app_id,                 # From my.telegram.org
    app_hash,               # From my.telegram.org
    proxy=proxy_tuple,      # Optional SOCKS5/HTTP proxy
    device_model=device,    # User agent
    system_version=sdk,
    app_version=app_version,
    lang_code=lang_pack,
)

await client.connect()
await client.is_user_authorized()
```

### Authentication Flow

1. **First login:**
   - `send_code_request(phone)` — Request SMS code
   - `sign_in(phone, code)` — Sign in with code
   - If 2FA: `sign_in(password=two_fa)` — Enter 2FA password

2. **Subsequent logins:**
   - Session file contains auth token
   - Automatic reauth via `connect()`

### Key Operations

| Operation | Telethon Method |
|-----------|-----------------|
| Get self | `client.get_me()` |
| Get entity | `client.get_entity(target)` |
| Send message | `client.send_message(target, text)` |
| Join channel | `JoinChannelRequest(entity)` |
| Leave channel | `LeaveChannelRequest(entity)` |
| Iterate dialogs | `client.iter_dialogs()` |
| Iterate messages | `client.iter_messages(entity)` |

### Rate Limiting

Telethon raises `FloodWaitError(seconds=N)` when rate limited.

**Handling:**
```python
try:
    await client.send_message(...)
except FloodWaitError as e:
    # Wait e.seconds before retry
    await asyncio.sleep(e.seconds + 5)
```

---

## Redis

### Connection

```python
import redis.asyncio as redis

client = redis.from_url("redis://localhost:6379")
```

### Task Queue

**Push task:**
```python
task = {"task_id": "...", "command": "...", "args": {...}}
await client.lpush(f"tasks:{profile}", json.dumps(task))
```

**Pop task:**
```python
result = await client.blpop([f"tasks:{profile}"], timeout=30)
if result:
    queue, task_json = result
    task = json.loads(task_json)
```

### Results

**Store result:**
```python
await client.setex(
    f"result:{task_id}",
    300,  # TTL seconds
    json.dumps(result)
)
```

**Get result:**
```python
result_json = await client.get(f"result:{task_id}")
if result_json:
    result = json.loads(result_json)
```

### Message Stream

**Publish:**
```python
await client.xadd(
    "tg:listener:messages",
    message.to_dict(),
    maxlen=1_000_000,
    approximate=True
)
```

**Consume (with consumer group):**
```python
# Create group (once)
try:
    await client.xgroup_create(
        "tg:listener:messages",
        "analyzers",
        id="0",
        mkstream=True
    )
except ResponseError:
    pass  # Group exists

# Read
messages = await client.xreadgroup(
    "analyzers",
    "consumer-1",
    {"tg:listener:messages": ">"},
    count=100,
    block=5000
)

# Acknowledge
await client.xack("tg:listener:messages", "analyzers", message_id)
```

### Heartbeats

**Update:**
```python
await client.setex(
    f"tg:listener:heartbeat:{listener_id}",
    30,  # TTL
    json.dumps({"account_id": 42, "timestamp": "..."})
)
```

**Check:**
```python
heartbeat = await client.get(f"tg:listener:heartbeat:{listener_id}")
if not heartbeat:
    # Listener is dead
```

---

## 2Captcha

### API Endpoints

- Submit: `http://2captcha.com/in.php`
- Result: `http://2captcha.com/res.php`

### Flow

```python
import aiohttp
import base64

# 1. Submit image
image_b64 = base64.b64encode(image_bytes).decode()
async with aiohttp.ClientSession() as session:
    resp = await session.post(
        "http://2captcha.com/in.php",
        data={
            "key": api_key,
            "method": "base64",
            "body": image_b64,
            "json": 1,
        }
    )
    data = await resp.json()
    captcha_id = data["request"]

# 2. Poll for result
for _ in range(12):  # 60 seconds max
    await asyncio.sleep(5)
    resp = await session.get(
        "http://2captcha.com/res.php",
        params={
            "key": api_key,
            "action": "get",
            "id": captcha_id,
            "json": 1,
        }
    )
    data = await resp.json()
    if data["status"] == 1:
        return data["request"]  # Solution text
```

### Configuration

| Env Variable | Description |
|--------------|-------------|
| `CAPTCHA_API_KEY` | 2Captcha API key |

---

## Anthropic Claude

### API Usage

```python
from anthropic import Anthropic

client = Anthropic(api_key=anthropic_api_key)

message = client.messages.create(
    model="claude-3-haiku-20240307",
    max_tokens=1024,
    messages=[
        {"role": "user", "content": prompt}
    ]
)

response_text = message.content[0].text
```

### Verification Prompt

The AI agent constructs prompts describing:
- Bot message text
- Available buttons
- Context (after_join, comment, etc.)

Claude returns structured response:
```json
{
  "is_verification": true,
  "action": {
    "type": "click_button",
    "button_index": 0
  },
  "confidence": 0.95,
  "reasoning": "..."
}
```

### Configuration

| Env Variable | Description |
|--------------|-------------|
| `ANTHROPIC_API_KEY` | Claude API key (sk-...) |

---

## Prometheus

### Metrics

```python
from prometheus_client import Counter, Histogram, push_to_gateway

# Define metrics
messages_sent = Counter(
    'tg_messages_sent_total',
    'Messages sent',
    ['status', 'operation']
)

# Record
messages_sent.labels(status='success', operation='message').inc()

# Push
push_to_gateway(
    gateway_url,
    job='tg-bot',
    registry=REGISTRY,
    handler=basic_auth_handler(username, password)
)
```

### Configuration

| Env Variable | Description |
|--------------|-------------|
| `PROMETHEUS_PUSH_GATEWAY` | Push gateway URL |
| `GRAFANA_CLOUD_USER` | Username (Grafana instance ID) |
| `GRAFANA_CLOUD_API_KEY` | API key |

---

## Grafana Loki

### Log Shipping

```python
import logging_loki

handler = logging_loki.LokiHandler(
    url=loki_url,
    auth=(username, api_key),
    tags={"application": "tg-bot"},
    version="1"
)

logger.addHandler(handler)
```

### Configuration

| Env Variable | Description |
|--------------|-------------|
| `LOKI_URL` | Loki ingestion URL |
| `GRAFANA_CLOUD_USER` | Username |
| `GRAFANA_CLOUD_API_KEY` | API key |

---

## Integration with tg-master

### Task Enqueue (tg-master → Redis)

```python
# In tg-master
task = {
    "task_id": str(uuid.uuid4()),
    "command": "join_channel",
    "args": {"channel": "https://t.me/channel"}
}
await redis.lpush(f"tasks:{profile}", json.dumps(task))
```

### Result Read (tg-master ← Redis)

```python
# In tg-master
result = await redis.get(f"result:{task_id}")
if result:
    data = json.loads(result)
    if data["status"] == "success":
        channel_id = data["result"]["channel_id"]
```

### Message Consumption (tg-master ← Redis Stream)

```python
# In tg-master
messages = await redis.xreadgroup(
    "analyzers",
    "consumer-1",
    {"tg:listener:messages": ">"},
    count=100,
    block=5000
)

for _, entries in messages:
    for entry_id, fields in entries:
        await process_message(fields)
        await redis.xack("tg:listener:messages", "analyzers", entry_id)
```

### Listener Health (tg-master ← Redis)

```python
# In tg-master
for listener_id in known_listeners:
    heartbeat = await redis.get(f"tg:listener:heartbeat:{listener_id}")
    if not heartbeat:
        await restart_listener(listener_id)
```
