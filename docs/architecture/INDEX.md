# Architecture Index

System design documentation for tg-bot.

## Overview

tg-bot is structured as a modular Python CLI application with:
- **Mixin-based client** for Telegram operations
- **Command pattern** for CLI interface
- **Worker/dispatcher** for distributed task execution
- **Event-driven listener** for real-time monitoring

## Documentation

| Document | Description |
|----------|-------------|
| [Module Structure](module-structure.md) | Package organization |
| [Data Models](data-models.md) | Dataclasses and schemas |
| [Configuration](configuration.md) | Environment and profiles |
| [Integrations](integrations.md) | External services |

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLI Layer                                │
│                                                                  │
│  cli.py → argparse → commands/*.py → run_command wrapper        │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Client Layer                               │
│                                                                  │
│  client.py (TgBot) ← ProfileMixin                               │
│                    ← ChannelsMixin                              │
│                    ← MessagesMixin                              │
│                    ← InfoMixin                                  │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Verification Layer                            │
│                                                                  │
│  ButtonVerification ← MathSolver                                │
│                     ← CaptchaSolver                             │
│                     ← PMVerification                            │
│  AIVerificationAgent ← VerificationCache                        │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                    External Services                             │
│                                                                  │
│  Telethon (Telegram) │ Redis │ 2Captcha │ Anthropic │ Metrics  │
└─────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

### CLI Layer (`cli.py`, `commands/`)

- Parse command-line arguments
- Route to appropriate command handler
- Handle errors and format output

### Client Layer (`client*.py`)

| Module | Responsibility |
|--------|----------------|
| `client.py` | Core TgBot class, connection, health check |
| `client_profile.py` | Profile CRUD operations |
| `client_channels.py` | Channel join/leave operations |
| `client_messages.py` | Message sending operations |
| `client_info.py` | Information retrieval |

### Verification Layer (`verification/`)

| Module | Responsibility |
|--------|----------------|
| `button.py` | Button click verification flow |
| `math_solver.py` | Arithmetic problem solving |
| `captcha.py` | 2Captcha API integration |
| `pm.py` | Private message verification |
| `ai_agent.py` | AI-powered verification |

### Worker Layer (`worker/`)

| Module | Responsibility |
|--------|----------------|
| `dispatcher.py` | Redis queue monitoring, subprocess spawning |
| `runner.py` | Single task execution |
| `handlers.py` | Task-to-operation mapping |
| `task.py` | Task/TaskResult data structures |

### Listener Layer (`listener/`)

| Module | Responsibility |
|--------|----------------|
| `listener.py` | Telegram event handling |
| `redis_stream.py` | Redis stream publishing, heartbeats |

### Utilities (`utils/`)

| Module | Responsibility |
|--------|----------------|
| `config.py` | Pydantic configuration models |
| `constants.py` | Timing and limit constants |
| `logger.py` | Logging setup and Loki integration |
| `metrics.py` | Prometheus metrics |
| `retry.py` | Retry decorators and utilities |
| `timeout.py` | Async timeout utilities |

## Design Principles

### 1. Mixin Composition
Client operations are split into focused mixins for maintainability. Each mixin handles a single concern.

### 2. Error Classification
Errors are classified as retryable vs permanent to enable smart retry logic upstream.

### 3. Subprocess Isolation
Task workers run in separate processes for clean state and resource isolation.

### 4. Human-like Timing
Random delays between operations to avoid detection and rate limiting.

### 5. Thread-safe Caching
Verification cache uses asyncio locks for concurrent access safety.
