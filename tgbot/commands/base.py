"""Base utilities for CLI commands."""

import asyncio
import json
import sys
from functools import wraps
from typing import Any, Callable, TypeVar

from ..utils.config import ConfigError
from ..utils.logger import setup_logger

log = setup_logger("tg-bot.cmd.base")

T = TypeVar("T")


def run_command(
    async_fn: Callable[..., Any],
    *,
    error_types: tuple[type[Exception], ...] = (),
    print_result: bool = True,
    result_key: str | None = None,
) -> Callable[..., Any | None]:
    """
    Wrapper for CLI commands that handles common patterns:
    - Runs async function with asyncio.run()
    - Handles ConfigError and custom error types
    - Optionally prints JSON result
    - Logs errors and exits with code 1 on failure

    Args:
        async_fn: The async function to wrap
        error_types: Additional exception types to catch (besides ConfigError)
        print_result: Whether to print the result as JSON
        result_key: If set, check this key in result dict to determine success

    Returns:
        Wrapper function that returns the result or None on error
    """

    @wraps(async_fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any | None:
        try:
            result = asyncio.run(async_fn(*args, **kwargs))

            if print_result and result is not None:
                if hasattr(result, "__dataclass_fields__"):
                    from dataclasses import asdict
                    print(json.dumps(asdict(result)))
                elif isinstance(result, dict):
                    print(json.dumps(result, indent=2))
                else:
                    print(json.dumps(result))

            return result

        except ConfigError as e:
            log.error(f"Configuration error: {e}")
            sys.exit(1)

        except error_types as e:
            error_name = type(e).__name__
            log.error(f"{error_name}: {e}")
            sys.exit(1)

        except Exception as e:
            log.error(f"Unexpected error: {e}")
            sys.exit(1)

    return wrapper
