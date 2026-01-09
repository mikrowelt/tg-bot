# TG-Bot

A Telegram CLI tool for channel management, messaging, and profile updates. Features automatic bot verification handling (button clicks, math problems, image captchas, PM verification).

## Installation

```bash
# Install dependencies
pip install -e .

# Or with pip directly
pip install telethon pysocks python-dotenv
```

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

| Variable | Description | Default |
|----------|-------------|---------|
| `PROFILE_NAME` | Profile file name (without extension) | `profile` |
| `BASE_DIR` | Base directory for profile files | `.` |
| `PROXY_TYPE` | Proxy type: SOCKS5, SOCKS4, HTTP | - |
| `PROXY_HOST` | Proxy server host | - |
| `PROXY_PORT` | Proxy server port | - |
| `PROXY_USERNAME` | Proxy authentication username | - |
| `PROXY_PASSWORD` | Proxy authentication password | - |
| `CAPTCHA_API_KEY` | 2Captcha API key for image captcha solving | - |
| `LOG_LEVEL` | Logging level: DEBUG, INFO, WARNING, ERROR | `INFO` |
| `LOG_FORMAT` | Log format: simple, detailed, json | `simple` |

### Profile Setup

Each profile requires two files in the base directory:

1. **`{PROFILE_NAME}.json`** - Account configuration:
```json
{
  "app_id": 123456,
  "app_hash": "your_app_hash",
  "phone": "+1234567890",
  "device": "Samsung Galaxy S21",
  "sdk": "SDK 31",
  "app_version": "8.9.0",
  "lang_pack": "en",
  "two_fa": "optional_2fa_password"
}
```

2. **`{PROFILE_NAME}.session`** - Telethon session file (created automatically on first login)

Get `app_id` and `app_hash` from [my.telegram.org](https://my.telegram.org).

## Usage

### Join Channel

Join a Telegram channel with automatic bot verification:

```bash
# Join by link
tg-bot join-channel https://t.me/channelname

# Join by username
tg-bot join-channel @channelname

# Join private channel
tg-bot join-channel https://t.me/+AbCdEfGhIjK

# Skip bot verification
tg-bot join-channel @channelname --skip-verification

# Use specific profile
tg-bot join-channel @channelname --profile myaccount
```

### Send Message

Send messages to channels, groups, or users:

```bash
# Send to channel/group
tg-bot send-message @channelname "Hello, world!"

# Send by channel ID
tg-bot send-message -1001234567890 "Hello!"

# Comment on a channel post
tg-bot send-message @channelname "Nice post!" --comment-to 123

# Reply to a message
tg-bot send-message @groupname "Reply text" --reply-to 456

# Use specific profile
tg-bot send-message @channelname "Hello" --profile myaccount
```

### Change Profile

Update Telegram profile information:

```bash
# Change first name
tg-bot change-profile --first-name "John"

# Change multiple fields
tg-bot change-profile --first-name "John" --last-name "Doe" --about "Developer"

# Change username
tg-bot change-profile --username "johndoe"

# Change profile photo
tg-bot change-profile --photo /path/to/photo.jpg

# Use specific profile
tg-bot change-profile --first-name "John" --profile myaccount
```

## Logging

### Log Levels

Set `LOG_LEVEL` in `.env`:

- **DEBUG** - Detailed information for debugging (button clicks, API calls)
- **INFO** - General operational messages (default)
- **WARNING** - Warning messages (failed captcha, rate limits)
- **ERROR** - Error messages only

### Log Formats

Set `LOG_FORMAT` in `.env`:

- **simple** - `LEVEL    | message`
- **detailed** - `timestamp | LEVEL    | module:func:line | message`
- **json** - `{"time": "...", "level": "...", "module": "...", "message": "..."}`

Example output with `LOG_LEVEL=DEBUG` and `LOG_FORMAT=detailed`:
```
2024-01-15 10:30:45 | INFO     | tg-bot.client:connect:42 | Connecting to Telegram...
2024-01-15 10:30:46 | DEBUG    | tg-bot.verification:verify:35 | Scanning channel for bots...
2024-01-15 10:30:47 | DEBUG    | tg-bot.verification:verify:52 | Found bot: Combot (@comaborot)
2024-01-15 10:30:49 | INFO     | tg-bot.verification:verify:98 | Clicked button 'Verify': OK
```

## Bot Verification

The tool automatically handles common anti-bot verification methods:

- **Button clicks** - Clicks callback buttons from verification bots
- **Math problems** - Solves simple math equations (e.g., "What is 2 + 2?")
- **Image captcha** - Solves via 2Captcha API (requires `CAPTCHA_API_KEY`)
- **PM verification** - Handles bots that require messaging them directly

## Project Structure

```
tg-bot/
├── src/
│   ├── cli.py              # CLI entry point
│   ├── client.py           # Main TgBot client
│   ├── commands/
│   │   ├── change_profile.py
│   │   ├── join_channel.py
│   │   └── send_message.py
│   ├── utils/
│   │   ├── config.py       # Configuration loading
│   │   └── logger.py       # Logging setup
│   └── verification/
│       ├── button.py       # Main verification handler
│       ├── captcha.py      # 2Captcha integration
│       ├── math_solver.py  # Math problem solver
│       └── pm.py           # PM verification
├── .env.example
├── pyproject.toml
└── README.md
```

## License

MIT
