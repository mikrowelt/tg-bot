# ADR-002: Subprocess Worker Isolation

## Status
Accepted

## Context

Running multiple Telegram accounts in a single process poses challenges:

1. **State leakage** — Telethon session state could cross-contaminate
2. **Error isolation** — Crash in one account affects others
3. **Resource cleanup** — Difficult to ensure clean teardown
4. **Memory** — Long-running processes accumulate state

Alternative approaches considered:
- **Thread pool** — Shared memory, GIL contention
- **Asyncio tasks** — Single process, shared state
- **Process pool** — Reused processes, state persistence
- **Subprocess per task** — Fresh process for each task

## Decision

Use **subprocess spawning** for task execution:

```python
# Dispatcher spawns fresh subprocess for each task
subprocess.Popen([
    "python", "-m", "tgbot.cli", "run-task",
    "--profile", profile_name,
    "--redis", redis_url,
])
```

Each task runs in a completely isolated process with:
- Fresh Python interpreter
- Fresh Telethon client
- Fresh session load
- Clean resource teardown on exit

## Consequences

### Benefits
- **Complete isolation** — No state shared between accounts
- **Clean cleanup** — Process exit releases all resources
- **Crash resilience** — Worker crash doesn't affect dispatcher
- **Simple debugging** — Each task is a standalone execution
- **Profile safety** — One profile, one process, one session

### Drawbacks
- **Startup overhead** — ~1-2 seconds per subprocess spawn
- **Connection overhead** — New Telethon connection each task
- **No connection reuse** — Can't batch operations on same connection
- **Process limit** — OS limit on concurrent processes

### Mitigation
- Accept overhead as acceptable for reliability
- Tasks already include human-like delays (2-6 seconds)
- Sequential execution per profile limits process count
- Connection overhead hidden within operation delays
