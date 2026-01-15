"""Logging configuration with optional Loki integration for Grafana Cloud."""

import os
import sys
import logging
import json
from datetime import datetime
from enum import Enum


class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


# Global Loki handler reference
_loki_handler = None


class JsonFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add function/line info for errors
        if record.levelno >= logging.ERROR:
            log_data["function"] = record.funcName
            log_data["line"] = record.lineno

        return json.dumps(log_data)


def configure_loki(
    loki_url: str | None = None,
    username: str | None = None,
    password: str | None = None,
    additional_labels: dict | None = None,
) -> bool:
    """
    Configure Loki log shipping for Grafana Cloud.

    For Grafana Cloud, use:
        loki_url: https://logs-prod-xx.grafana.net/loki/api/v1/push
        username: Your Grafana Cloud instance ID
        password: Your Grafana Cloud API key

    Args:
        loki_url: Loki push API URL (or LOKI_URL env var)
        username: Basic auth username (or GRAFANA_CLOUD_USER env var)
        password: Basic auth password (or GRAFANA_CLOUD_API_KEY env var)
        additional_labels: Extra labels to add to all logs

    Returns:
        True if Loki was configured successfully
    """
    global _loki_handler

    loki_url = loki_url or os.getenv("LOKI_URL")
    username = username or os.getenv("GRAFANA_CLOUD_USER")
    password = password or os.getenv("GRAFANA_CLOUD_API_KEY")

    if not loki_url:
        return False

    try:
        import logging_loki

        # Build labels
        labels = {
            "app": "tg-bot",
            "env": os.getenv("ENVIRONMENT", "development"),
        }
        if additional_labels:
            labels.update(additional_labels)

        # Build auth tuple if credentials provided
        auth = (username, password) if username and password else None

        # Create Loki handler
        _loki_handler = logging_loki.LokiHandler(
            url=loki_url,
            tags=labels,
            auth=auth,
            version="1",
        )
        _loki_handler.setLevel(logging.DEBUG)

        # Add to root tg-bot logger
        root_logger = logging.getLogger("tg-bot")
        root_logger.addHandler(_loki_handler)

        logging.getLogger("tg-bot.logger").info(
            f"Loki configured: {loki_url} with labels {labels}"
        )
        return True

    except ImportError:
        logging.getLogger("tg-bot.logger").debug(
            "python-logging-loki not installed, Loki disabled"
        )
        return False
    except Exception as e:
        logging.getLogger("tg-bot.logger").warning(f"Failed to configure Loki: {e}")
        return False


def setup_logger(name: str = "tg-bot") -> logging.Logger:
    """
    Setup and return a configured logger.

    Log level is controlled by LOG_LEVEL env var (default: INFO).
    Log format is controlled by LOG_FORMAT env var (default: simple).
    """
    # Get or create logger
    logger = logging.getLogger(name)

    # Only configure the root tg-bot logger, children will propagate
    root_logger = logging.getLogger("tg-bot")
    if root_logger.handlers:
        return logger

    # Get log level from env
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    try:
        level = getattr(logging, level_name)
    except AttributeError:
        level = logging.INFO

    root_logger.setLevel(level)

    # Create console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    # Format based on env
    log_format = os.getenv("LOG_FORMAT", "simple")
    if log_format == "json":
        formatter = JsonFormatter()
    elif log_format == "detailed":
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
    else:  # simple
        formatter = logging.Formatter(
            "%(levelname)-8s | %(message)s"
        )

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Prevent propagation to root logger to avoid duplicate output
    root_logger.propagate = False

    return logger


class LoggerAdapter(logging.LoggerAdapter):
    """Logger adapter that adds extra context to all log messages."""

    def process(self, msg, kwargs):
        # Add extra fields for structured logging
        extra = kwargs.get("extra", {})
        extra["extra_fields"] = self.extra
        kwargs["extra"] = extra
        return msg, kwargs


def get_logger_with_context(name: str, **context) -> LoggerAdapter:
    """
    Get a logger with additional context fields.

    Usage:
        log = get_logger_with_context("tg-bot.client", profile="user123", channel="test")
        log.info("Joining channel")  # Will include profile and channel in structured logs
    """
    logger = setup_logger(name)
    return LoggerAdapter(logger, context)


# Initialize root logger on import
setup_logger("tg-bot")
