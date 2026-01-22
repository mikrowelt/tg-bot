# TG-Bot Documentation

**tg-bot** is a Python CLI tool for Telegram account automation built on Telethon. It provides channel management, profile operations, message sending, and automatic bot verification handling.

## Quick Links

| Section | Description |
|---------|-------------|
| [Requirements](requirements/INDEX.md) | Feature specifications |
| [Architecture](architecture/INDEX.md) | System design & components |
| [Decisions](decisions/INDEX.md) | Architecture Decision Records |

## Key Capabilities

- **Profile Management** — Update name, bio, username, photos
- **Channel Operations** — Join/leave channels, check membership, ban detection
- **Message Sending** — Direct messages, comments, reactions, forum topics
- **Bot Verification** — Automatic handling of math captchas, buttons, AI-powered verification
- **Task Queue** — Redis-based distributed task execution across multiple accounts
- **Message Listener** — Real-time group monitoring with Redis stream publishing

## Technology Stack

| Component | Technology |
|-----------|------------|
| Telegram API | Telethon 1.42+ |
| Task Queue | Redis 5.0+ |
| Configuration | Pydantic 2.0+ |
| AI Verification | Anthropic Claude API |
| Captcha Solving | 2Captcha API |
| Monitoring | Prometheus + Grafana Loki |

## Getting Started

```bash
# Install
pip install -e .

# Configure profile
cp profile.example.json profile.json
# Edit profile.json with your Telegram app credentials

# Run health check
tg-bot health-check

# Join a channel
tg-bot join-channel https://t.me/channelname

# Send a message
tg-bot send-message @username "Hello!"
```

## Environment Variables

See [Architecture > Configuration](architecture/configuration.md) for complete list.

**Required:**
- `PROFILE_NAME` — Profile file name (default: "profile")
- `BASE_DIR` — Directory containing profiles (default: ".")

**Optional:**
- `CAPTCHA_API_KEY` — 2Captcha API key
- `ANTHROPIC_API_KEY` — For AI verification
- `REDIS_URL` — Redis connection (for worker/listener)
- `PROXY_TYPE`, `PROXY_HOST`, `PROXY_PORT` — Proxy configuration

## Integration with tg-master

This tool is designed to work with **tg-master** (orchestrator):

1. **Direct CLI calls** — Subprocess execution of commands
2. **Task Queue** — Redis-based async task execution
3. **Message Stream** — Real-time message forwarding via Redis streams
4. **Heartbeats** — Listener health monitoring

See [Architecture > Integrations](architecture/integrations.md) for details.
