# Monitoring & Observability

## Overview

Monitoring stack for tg-bot using Prometheus metrics and Grafana Loki for logs.

## Components

### Prometheus Metrics (`tgbot/utils/metrics.py`)

Push-based metrics collection to Prometheus Push Gateway (compatible with Grafana Cloud).

### Grafana Loki Logging (`tgbot/utils/logger.py`)

Structured logging with optional Loki integration for centralized log aggregation.

---

## Metrics System

### Configuration

```python
from tgbot.utils.metrics import configure_metrics

configure_metrics(
    push_gateway_url="https://prometheus-prod-xx.grafana.net/api/prom/push",
    job_name="tg-bot",
    username=None,  # Uses GRAFANA_CLOUD_USER env
    password=None,  # Uses GRAFANA_CLOUD_API_KEY env
)
```

### Key Functions

```python
def configure_metrics(
    push_gateway_url: str | None = None,
    job_name: str = "tg-bot",
    username: str | None = None,
    password: str | None = None,
) -> None:
    """Configure Prometheus metrics push gateway."""

def push_metrics() -> bool:
    """Push current metrics to the push gateway."""
```

### Available Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `tgbot_messages_sent_total` | Counter | status, target_type | Total messages sent |
| `tgbot_message_send_duration_seconds` | Histogram | target_type | Message send latency |
| `tgbot_channel_joins_total` | Counter | status | Channel join attempts |
| `tgbot_channel_join_duration_seconds` | Histogram | - | Join operation latency |
| `tgbot_verifications_total` | Counter | type, status | Verification attempts |
| `tgbot_rate_limits_total` | Counter | operation | Rate limit errors |
| `tgbot_rate_limit_wait_seconds` | Histogram | operation | Rate limit wait times |
| `tgbot_errors_total` | Counter | error_type, operation | Errors by type |
| `tgbot_active_operations` | Gauge | operation | Active operations |
| `tgbot_profile_updates_total` | Counter | field, status | Profile updates |

### Recording Functions

```python
def record_message_sent(status: str, target_type: str = "unknown", duration: float = 0):
    """Record a message send operation."""

def record_channel_join(status: str, duration: float = 0):
    """Record a channel join operation."""

def record_verification(verification_type: str, status: str):
    """Record a verification attempt."""

def record_rate_limit(operation: str, wait_seconds: int):
    """Record a rate limit error."""

def record_error(error_type: str, operation: str):
    """Record an error."""

def record_profile_update(field: str, status: str):
    """Record a profile update operation."""
```

### Decorators

```python
@track_duration(histogram, **labels)
async def my_operation():
    """Decorator to track function duration."""

@track_operation("operation_name")
async def my_operation():
    """Decorator to track active operations gauge."""
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `PROMETHEUS_PUSH_GATEWAY` | Push gateway URL |
| `GRAFANA_CLOUD_USER` | Grafana Cloud instance ID |
| `GRAFANA_CLOUD_API_KEY` | Grafana Cloud API key |

---

## Logging System

### Configuration

```python
from tgbot.utils.logger import setup_logger, configure_loki

# Basic logger
log = setup_logger("tg-bot.mymodule")

# Configure Loki (optional)
configure_loki(
    loki_url="https://logs-prod-xx.grafana.net/loki/api/v1/push",
    username=None,  # Uses GRAFANA_CLOUD_USER env
    password=None,  # Uses GRAFANA_CLOUD_API_KEY env
    additional_labels={"service": "tg-bot"},
)
```

### Key Classes

```python
class LogLevel(Enum):
    """Log level enumeration."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"

class JsonFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

class LoggerAdapter(logging.LoggerAdapter):
    """Logger adapter that adds extra context to all log messages."""
```

### Key Functions

```python
def setup_logger(name: str = "tg-bot") -> logging.Logger:
    """
    Setup and return a configured logger.

    Log level: LOG_LEVEL env var (default: INFO)
    Log format: LOG_FORMAT env var (default: simple)
    """

def configure_loki(
    loki_url: str | None = None,
    username: str | None = None,
    password: str | None = None,
    additional_labels: dict | None = None,
) -> bool:
    """Configure Loki log shipping for Grafana Cloud."""

def get_logger_with_context(name: str, **context) -> LoggerAdapter:
    """Get a logger with additional context fields."""
```

### Log Formats

| Format | Environment | Output |
|--------|-------------|--------|
| `simple` | Development | `INFO     | Message text` |
| `detailed` | Debug | `2024-01-15 12:34:56 | INFO     | name:func:42 | Message` |
| `json` | Production | `{"timestamp": "...", "level": "INFO", "message": "..."}` |

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | DEBUG, INFO, WARNING, ERROR |
| `LOG_FORMAT` | `simple` | simple, detailed, json |
| `LOKI_URL` | None | Loki push API URL |
| `GRAFANA_CLOUD_USER` | None | Grafana Cloud instance ID |
| `GRAFANA_CLOUD_API_KEY` | None | Grafana Cloud API key |
| `ENVIRONMENT` | `development` | Environment label for logs |

### Usage Examples

```python
from tgbot.utils.logger import setup_logger, get_logger_with_context

# Basic usage
log = setup_logger("tg-bot.client")
log.info("Operation completed")
log.error("Operation failed", exc_info=True)

# With context
log = get_logger_with_context("tg-bot.client", profile="user123", channel="test")
log.info("Joining channel")  # Includes profile and channel in JSON logs
```

---

## Listener Heartbeat System

### Overview

The listener process sends periodic heartbeats to Redis for health monitoring.

### Classes (`tgbot/listener/redis_stream.py`)

```python
class HeartbeatManager:
    """Manages periodic heartbeats to Redis."""

    async def start(self) -> None:
        """Start the heartbeat background task."""

    async def stop(self) -> None:
        """Stop the heartbeat task."""

    async def _send_heartbeat(self) -> None:
        """Send a single heartbeat to Redis."""
```

### Redis Keys

| Key | TTL | Value |
|-----|-----|-------|
| `tg:listener:heartbeat:{listener_id}` | 30s | JSON: `{account_id, timestamp, groups}` |

### Monitoring from tg-master

```python
# Check listener health
heartbeat = await redis.get(f"tg:listener:heartbeat:{listener_id}")
if not heartbeat:
    # Listener dead - no heartbeat for 30s
    await restart_listener(listener_id)
```

---

## Grafana Cloud Integration

### Setup

1. Create Grafana Cloud account
2. Get Prometheus Push Gateway URL
3. Get Loki Push API URL
4. Create API key with push permissions

### Environment Configuration

```bash
# Grafana Cloud credentials
export GRAFANA_CLOUD_USER="your-instance-id"
export GRAFANA_CLOUD_API_KEY="your-api-key"

# Prometheus
export PROMETHEUS_PUSH_GATEWAY="https://prometheus-prod-xx.grafana.net/api/prom/push"

# Loki
export LOKI_URL="https://logs-prod-xx.grafana.net/loki/api/v1/push"

# Log format for production
export LOG_FORMAT="json"
export ENVIRONMENT="production"
```

---

## Dashboard Queries

### Grafana Prometheus

```promql
# Message send rate
rate(tgbot_messages_sent_total[5m])

# Average join duration
histogram_quantile(0.95, rate(tgbot_channel_join_duration_seconds_bucket[5m]))

# Error rate
rate(tgbot_errors_total[5m])
```

### Grafana Loki

```logql
# All tg-bot logs
{app="tg-bot"}

# Errors only
{app="tg-bot"} |= "ERROR"

# Specific profile
{app="tg-bot"} | json | profile="user123"
```
