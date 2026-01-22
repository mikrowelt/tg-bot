# Changelog

All notable changes to tg-bot are documented in this file.

## [Unreleased]

### Fixed
- **Listener signal handler** now properly awaits async disconnect to prevent "database is locked" SQLite errors

### Added
- **Dev branch deployment support** for CI/CD pipeline
- **Centralized constants module** (`tgbot/utils/constants.py`) for all magic numbers and timeouts
- **Retry utilities** (`tgbot/utils/retry.py`) with exponential backoff and `RetryContext`
- **Timeout utilities** (`tgbot/utils/timeout.py`) with decorators and context managers
- **Client mixin modules** for better code organization:
  - `client_channels.py` - channel operations
  - `client_info.py` - info retrieval methods
  - `client_messages.py` - messaging operations
- **Button verification tests** and **constants tests** for improved coverage
- **Listen command** for real-time message monitoring via Redis streams
- **Supergroup and forum topic support** for enhanced channel handling
- **Check-all-bans command** for health score tracking across all channels
- **Reaction capability** for warmup activities
- **Check-ban command** for single channel ban detection
- **Comments_enabled detection** in `get_channel_info`
- **Private channel membership check** (`check_channel_membership`)
- **Metrics and monitoring support** for observability
- **Reply chains** in channel comments with `reply_to` parameter
- **Rate limit handling** for `set_username` with retry for taken usernames
- **Terminate other sessions** method for security
- **Configurable `posts_limit` and `text_length`** for `get_channel_info`
- **Leave channel method** with improved error handling
- **Verification check** for post comments and linked discussion groups
- **Auto-join linked discussion group** when joining channels
- **AI-powered verification agent** using Claude (Anthropic)
- **Verify in comments** method for bot verification handling
- **Multi-photo upload and delete** methods
- **Get joined channels** and **get profile photos** methods

### Changed
- **Refactored `client.py`** using mixin pattern — split into `client_channels.py`, `client_info.py`, `client_messages.py`, `client_profile.py`
- **Extracted magic numbers** into `constants.py` with named constants for wait times, timeouts, and retry config
- Renamed `src` to `tgbot` to avoid namespace conflict

### Fixed
- Group filtering in listener with correct ID extraction
- Math captcha caching bug that sent wrong answers
- @AntiSpamGlobalBot verification to check discussion group
- Leave channel to handle both channels and groups

## [2026-01-18]

### Added
- Listen command for real-time monitoring
- Check-all-bans and check-ban commands
- Reaction capability for warmup

### Fixed
- Config.profile attribute error in listener

## [2026-01-14]

### Added
- AI verification agent
- Reply threading support
- Channel info methods
- Session management

## [2026-01-12]

### Added
- Photo management methods
- Target type detection
- Verification in comments

### Changed
- Project structure refactoring

## [2026-01-09]

### Added
- Initial release
- Core Telegram client with Telethon
- Profile management (get/apply)
- Channel operations (join, leave, send messages)
- Verification handlers (button, math, captcha, PM)
- CLI interface

---

For full commit history, see [GitHub](https://github.com/mikrowelt/tg-bot/commits/main).
