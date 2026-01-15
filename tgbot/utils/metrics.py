"""Prometheus metrics for Grafana Cloud integration."""

import os
import atexit
from functools import wraps
from typing import Callable, Any

from .logger import setup_logger

log = setup_logger("tg-bot.metrics")

# Try to import prometheus_client, but don't fail if not installed
try:
    from prometheus_client import (
        Counter,
        Histogram,
        Gauge,
        CollectorRegistry,
        push_to_gateway,
        generate_latest,
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    log.debug("prometheus-client not installed, metrics disabled")


# Global registry
_registry = CollectorRegistry() if PROMETHEUS_AVAILABLE else None
_push_gateway_url: str | None = None
_job_name: str = "tg-bot"


def configure_metrics(
    push_gateway_url: str | None = None,
    job_name: str = "tg-bot",
    username: str | None = None,
    password: str | None = None,
) -> None:
    """
    Configure Prometheus metrics push gateway.

    For Grafana Cloud, use:
        push_gateway_url: https://prometheus-prod-xx-prod-xx.grafana.net/api/prom/push
        username: Your Grafana Cloud instance ID
        password: Your Grafana Cloud API key

    Args:
        push_gateway_url: Prometheus push gateway URL (or PROMETHEUS_PUSH_GATEWAY env var)
        job_name: Job name for metrics grouping
        username: Basic auth username (or GRAFANA_CLOUD_USER env var)
        password: Basic auth password (or GRAFANA_CLOUD_API_KEY env var)
    """
    global _push_gateway_url, _job_name

    if not PROMETHEUS_AVAILABLE:
        log.warning("Metrics not configured: prometheus-client not installed")
        return

    _push_gateway_url = push_gateway_url or os.getenv("PROMETHEUS_PUSH_GATEWAY")
    _job_name = job_name

    if _push_gateway_url:
        log.info(f"Metrics configured: push_gateway={_push_gateway_url}, job={_job_name}")

        # Register atexit handler to push final metrics
        atexit.register(_push_metrics_on_exit)
    else:
        log.debug("No push gateway configured, metrics will only be available locally")


def _get_auth_handler():
    """Get basic auth handler for Grafana Cloud."""
    username = os.getenv("GRAFANA_CLOUD_USER")
    password = os.getenv("GRAFANA_CLOUD_API_KEY")

    if username and password:
        from urllib.request import HTTPBasicAuthHandler, build_opener

        auth_handler = HTTPBasicAuthHandler()
        auth_handler.add_password(
            realm=None,
            uri=_push_gateway_url,
            user=username,
            passwd=password,
        )
        return build_opener(auth_handler)
    return None


def push_metrics() -> bool:
    """
    Push current metrics to the push gateway.

    Returns True if successful, False otherwise.
    """
    if not PROMETHEUS_AVAILABLE or not _push_gateway_url:
        return False

    try:
        handler = _get_auth_handler()
        push_to_gateway(
            _push_gateway_url,
            job=_job_name,
            registry=_registry,
            handler=handler,
        )
        log.debug("Metrics pushed successfully")
        return True
    except Exception as e:
        log.warning(f"Failed to push metrics: {e}")
        return False


def _push_metrics_on_exit():
    """Push metrics on process exit."""
    if _push_gateway_url:
        push_metrics()


# ============ METRICS DEFINITIONS ============

if PROMETHEUS_AVAILABLE:
    # Message metrics
    MESSAGES_SENT = Counter(
        "tgbot_messages_sent_total",
        "Total messages sent",
        ["status", "target_type"],
        registry=_registry,
    )

    MESSAGE_SEND_DURATION = Histogram(
        "tgbot_message_send_duration_seconds",
        "Message send duration in seconds",
        ["target_type"],
        buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
        registry=_registry,
    )

    # Channel operations
    CHANNEL_JOINS = Counter(
        "tgbot_channel_joins_total",
        "Total channel join attempts",
        ["status"],
        registry=_registry,
    )

    CHANNEL_JOIN_DURATION = Histogram(
        "tgbot_channel_join_duration_seconds",
        "Channel join duration in seconds",
        buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0],
        registry=_registry,
    )

    # Verification metrics
    VERIFICATIONS = Counter(
        "tgbot_verifications_total",
        "Total verification attempts",
        ["type", "status"],
        registry=_registry,
    )

    # Rate limiting
    RATE_LIMITS = Counter(
        "tgbot_rate_limits_total",
        "Total rate limit errors",
        ["operation"],
        registry=_registry,
    )

    RATE_LIMIT_WAIT_SECONDS = Histogram(
        "tgbot_rate_limit_wait_seconds",
        "Rate limit wait time in seconds",
        ["operation"],
        buckets=[1, 5, 10, 30, 60, 120, 300, 600],
        registry=_registry,
    )

    # Errors
    ERRORS = Counter(
        "tgbot_errors_total",
        "Total errors by type",
        ["error_type", "operation"],
        registry=_registry,
    )

    # Active operations gauge
    ACTIVE_OPERATIONS = Gauge(
        "tgbot_active_operations",
        "Currently active operations",
        ["operation"],
        registry=_registry,
    )

    # Profile operations
    PROFILE_UPDATES = Counter(
        "tgbot_profile_updates_total",
        "Total profile update attempts",
        ["field", "status"],
        registry=_registry,
    )

else:
    # Dummy metrics when prometheus not available
    class DummyMetric:
        def labels(self, *args, **kwargs):
            return self

        def inc(self, *args, **kwargs):
            pass

        def dec(self, *args, **kwargs):
            pass

        def observe(self, *args, **kwargs):
            pass

        def set(self, *args, **kwargs):
            pass

    MESSAGES_SENT = DummyMetric()
    MESSAGE_SEND_DURATION = DummyMetric()
    CHANNEL_JOINS = DummyMetric()
    CHANNEL_JOIN_DURATION = DummyMetric()
    VERIFICATIONS = DummyMetric()
    RATE_LIMITS = DummyMetric()
    RATE_LIMIT_WAIT_SECONDS = DummyMetric()
    ERRORS = DummyMetric()
    ACTIVE_OPERATIONS = DummyMetric()
    PROFILE_UPDATES = DummyMetric()


# ============ HELPER DECORATORS ============

def track_duration(histogram, **labels):
    """Decorator to track function duration."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            if PROMETHEUS_AVAILABLE:
                with histogram.labels(**labels).time():
                    return await func(*args, **kwargs)
            return await func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            if PROMETHEUS_AVAILABLE:
                with histogram.labels(**labels).time():
                    return func(*args, **kwargs)
            return func(*args, **kwargs)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def track_operation(operation_name: str):
    """Decorator to track active operations."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            ACTIVE_OPERATIONS.labels(operation=operation_name).inc()
            try:
                return await func(*args, **kwargs)
            finally:
                ACTIVE_OPERATIONS.labels(operation=operation_name).dec()

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            ACTIVE_OPERATIONS.labels(operation=operation_name).inc()
            try:
                return func(*args, **kwargs)
            finally:
                ACTIVE_OPERATIONS.labels(operation=operation_name).dec()

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# ============ CONVENIENCE FUNCTIONS ============

def record_message_sent(status: str, target_type: str = "unknown", duration: float = 0):
    """Record a message send operation."""
    MESSAGES_SENT.labels(status=status, target_type=target_type).inc()
    if duration > 0:
        MESSAGE_SEND_DURATION.labels(target_type=target_type).observe(duration)


def record_channel_join(status: str, duration: float = 0):
    """Record a channel join operation."""
    CHANNEL_JOINS.labels(status=status).inc()
    if duration > 0:
        CHANNEL_JOIN_DURATION.observe(duration)


def record_verification(verification_type: str, status: str):
    """Record a verification attempt."""
    VERIFICATIONS.labels(type=verification_type, status=status).inc()


def record_rate_limit(operation: str, wait_seconds: int):
    """Record a rate limit error."""
    RATE_LIMITS.labels(operation=operation).inc()
    RATE_LIMIT_WAIT_SECONDS.labels(operation=operation).observe(wait_seconds)


def record_error(error_type: str, operation: str):
    """Record an error."""
    ERRORS.labels(error_type=error_type, operation=operation).inc()


def record_profile_update(field: str, status: str):
    """Record a profile update operation."""
    PROFILE_UPDATES.labels(field=field, status=status).inc()
