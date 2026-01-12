import os
import sys
import logging
from enum import Enum


class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


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
    if log_format == "detailed":
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
    elif log_format == "json":
        formatter = logging.Formatter(
            '{"time": "%(asctime)s", "level": "%(levelname)s", "module": "%(name)s", "message": "%(message)s"}'
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


# Initialize root logger on import
setup_logger("tg-bot")
