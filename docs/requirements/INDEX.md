# Requirements Index

Feature specifications for tg-bot.

## Feature Categories

### Core Operations

| Feature | Status | Documentation |
|---------|--------|---------------|
| CLI Interface | Active | [cli-commands.md](cli-commands.md) |
| Profile Management | Active | [profile-management.md](profile-management.md) |
| Channel Operations | Active | [channel-operations.md](channel-operations.md) |
| Message Sending | Active | [message-sending.md](message-sending.md) |

### Automation

| Feature | Status | Documentation |
|---------|--------|---------------|
| Bot Verification | Active | [verification.md](verification.md) |
| Task Queue Worker | Active | [worker-dispatcher.md](worker-dispatcher.md) |
| Message Listener | Active | [listener.md](listener.md) |

### Infrastructure

| Feature | Status | Documentation |
|---------|--------|---------------|
| Configuration | Active | [configuration.md](configuration.md) |
| Monitoring | Active | [monitoring.md](monitoring.md) |
| Utilities | Active | [utilities.md](utilities.md) |

## Feature Summary

### CLI Interface
11 user-facing commands + 2 internal commands for task execution.

### Profile Management
Full CRUD for Telegram profile: name, bio, username, photos.

### Channel Operations
Join/leave channels, check membership, detect bans, list forum topics.

### Message Sending
Send to users/groups/channels, reply to messages, comment on posts, send reactions, forum topic support.

### Bot Verification
Automatic handling of join verification: math captchas, button clicks, image captchas, PM verification, AI-powered analysis.

### Task Queue Worker
Redis-based distributed task execution with subprocess isolation.

### Message Listener
Real-time Telegram group monitoring with Redis stream publishing.

### Configuration
Pydantic-validated configuration from JSON profiles and environment variables.

### Monitoring
Prometheus metrics, Grafana Loki logging, heartbeat system for listeners.

### Utilities
Centralized constants, retry utilities with exponential backoff, async timeout wrappers.
