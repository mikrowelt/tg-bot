# Worker & Dispatcher System

## Overview

Redis-based distributed task execution system for running Telegram operations across multiple accounts with subprocess isolation.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     tg-master (orchestrator)                 │
│                                                              │
│  LPUSH tasks:profile1 {"task_id":"...", "command":"..."}    │
└───────────────────────────────┬─────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│                         Redis                                │
│                                                              │
│  tasks:profile1  [task1, task2, ...]                        │
│  tasks:profile2  [task3, task4, ...]                        │
│  result:task_id  {"status":"success", "result":{...}}       │
└───────────────────────────────┬─────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│                    Dispatcher (tg-bot worker)                │
│                                                              │
│  BLPOP tasks:profile1, tasks:profile2  (timeout=1s)         │
│                                                              │
│  For each task:                                              │
│    1. LPUSH task back to queue                              │
│    2. Spawn subprocess: tg-bot run-task --profile X         │
│    3. Monitor subprocess                                     │
└───────────────────────────────┬─────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────┐
│                    Worker Subprocess                         │
│                                                              │
│  1. BLPOP task from queue                                   │
│  2. Load profile Config                                      │
│  3. Connect TgBot                                           │
│  4. Execute handler                                          │
│  5. SETEX result:task_id (with TTL)                         │
└─────────────────────────────────────────────────────────────┘
```

## Task Structure

### Task

```python
@dataclass
class Task:
    task_id: str              # Unique identifier (UUID)
    command: Command          # Enum: JOIN_CHANNEL, SEND_MESSAGE, etc.
    args: dict[str, Any]      # Command-specific arguments
```

### Supported Commands

| Command | Arguments |
|---------|-----------|
| `join_channel` | `channel`, `skip_verification?` |
| `send_message` | `target`, `text`, `reply_to?`, `comment_to?` |
| `change_profile` | `first_name?`, `last_name?`, `about?`, `username?`, `photo?` |
| `get_profile` | `include_photo?` |
| `profile_health_check` | `expected_first_name?`, `expected_last_name?`, `expected_username?`, `expected_about?` |

### TaskResult

```python
@dataclass
class TaskResult:
    task_id: str
    status: TaskStatus        # SUCCESS or ERROR
    result: dict | None       # Command output (if success)
    error: str | None         # Error message (if error)
    error_type: str | None    # Exception class name
```

## Dispatcher

### Configuration

```bash
tg-bot worker \
  --profiles profile1,profile2,profile3 \
  --redis redis://localhost:6379 \
  --result-ttl 300
```

| Option | Default | Description |
|--------|---------|-------------|
| `--profiles` | Required | Comma-separated profile names |
| `--all` | - | Watch all profiles in BASE_DIR |
| `--redis` | `redis://localhost:6379` | Redis URL |
| `--result-ttl` | 300 | Result TTL in seconds |

### Behavior

**Queue Selection:**
- Only profiles without active workers are polled
- One worker per profile at a time (sequential execution)
- Round-robin across available profiles

**Subprocess Spawning:**
```bash
python -m tgbot.cli run-task \
  --profile <profile_name> \
  --redis <redis_url> \
  --result-ttl <ttl>
```

**Shutdown:**
- SIGINT/SIGTERM triggers graceful shutdown
- Waits up to 30 seconds for active workers
- Closes Redis connection

### Error Handling

| Scenario | Behavior |
|----------|----------|
| Worker subprocess fails | Logged, profile available for next task |
| Redis connection lost | Reconnect with backoff |
| Task execution error | Result stored with ERROR status |

## Task Runner

### Execution Flow

```python
async def run_single_task():
    # 1. Pop task from queue
    task = await pop_task(queue_key, timeout=30)
    if not task:
        return False  # No task available

    # 2. Load configuration
    config = Config.load(profile_name)

    # 3. Connect to Telegram
    async with TgBot(config) as bot:
        # 4. Execute task
        result = await execute_task(bot, task)

    # 5. Store result
    await store_result(task.task_id, result, ttl=result_ttl)
    return True
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Task executed successfully |
| 1 | Error during execution |
| 2 | No task in queue (timeout) |

## Task Handlers

### Handler Mapping

```python
HANDLERS = {
    Command.JOIN_CHANNEL: handle_join_channel,
    Command.SEND_MESSAGE: handle_send_message,
    Command.CHANGE_PROFILE: handle_change_profile,
    Command.GET_PROFILE: handle_get_profile,
    Command.PROFILE_HEALTH_CHECK: handle_profile_health_check,
}
```

### Handler Examples

**join_channel:**
```python
async def handle_join_channel(bot, args):
    channel_id = await bot.join_channel(
        channel_link=args["channel"],
        verify=not args.get("skip_verification", False),
    )
    return {"channel_id": channel_id}
```

**send_message:**
```python
async def handle_send_message(bot, args):
    if args.get("comment_to"):
        result = await bot.send_comment(
            args["target"],
            args["comment_to"],
            args["text"]
        )
    else:
        result = await bot.send_message(
            args["target"],
            args["text"],
            reply_to=args.get("reply_to")
        )
    return asdict(result)
```

## Redis Keys

| Key Pattern | Type | TTL | Description |
|-------------|------|-----|-------------|
| `tasks:{profile}` | List | None | Task queue per profile |
| `result:{task_id}` | String | 300s | Task result (JSON) |

## Integration with tg-master

### Enqueueing Tasks

```python
# tg-master pushes task
task = {
    "task_id": str(uuid.uuid4()),
    "command": "join_channel",
    "args": {"channel": "https://t.me/channel"}
}
redis.lpush(f"tasks:{profile}", json.dumps(task))
```

### Reading Results

```python
# tg-master reads result
result_json = redis.get(f"result:{task_id}")
if result_json:
    result = json.loads(result_json)
    if result["status"] == "success":
        channel_id = result["result"]["channel_id"]
```

## Concurrency Model

**Guarantees:**
- Single task execution per profile
- No concurrent modifications to same account
- Clean subprocess isolation
- No shared state between tasks

**Limitations:**
- Sequential execution (no parallel tasks per profile)
- Subprocess overhead (~1-2 seconds per task)
