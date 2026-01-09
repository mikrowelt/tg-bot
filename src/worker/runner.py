import asyncio
import json
import sys

import redis.asyncio as redis

from ..client import TgBot
from ..utils.config import Config, ConfigError
from ..utils.logger import setup_logger
from .task import Task, TaskResult
from .handlers import execute_task

log = setup_logger("tg-bot.worker.runner")


async def run_single_task(
    profile: str,
    redis_url: str,
    result_ttl: int = 300,
    timeout: int = 5,
) -> bool:
    """
    Pop and execute a single task from the profile's queue.

    Args:
        profile: Profile name
        redis_url: Redis connection URL
        result_ttl: Seconds to keep result in Redis
        timeout: Seconds to wait for a task (0 = no wait, just check)

    Returns:
        True if a task was executed, False if queue was empty
    """
    r = await redis.from_url(redis_url, decode_responses=False)
    queue = f"tasks:{profile}"

    try:
        # Pop task from queue
        if timeout > 0:
            result = await r.blpop(queue, timeout=timeout)
        else:
            result = await r.lpop(queue)
            if result:
                result = (queue.encode(), result)

        if not result:
            log.debug(f"No tasks in queue for {profile}")
            return False

        _, task_data = result
        task = Task.from_json(task_data)
        log.info(f"Executing task {task.task_id}: {task.command.value}")

        # Connect and execute
        try:
            config = Config.load(profile)
            bot = TgBot(config)
            await bot.connect()

            try:
                task_result = await execute_task(bot, task)
            finally:
                await bot.disconnect()

        except ConfigError as e:
            log.error(f"Config error: {e}")
            task_result = TaskResult.failure(task.task_id, str(e), "ConfigError")
        except Exception as e:
            log.error(f"Execution error: {e}")
            task_result = TaskResult.failure(task.task_id, str(e), type(e).__name__)

        # Store result
        result_key = f"result:{task.task_id}"
        await r.setex(result_key, result_ttl, task_result.to_json())
        log.info(f"Task {task.task_id} completed: {task_result.status.value}")

        return True

    finally:
        await r.close()


def run_task_sync(
    profile: str,
    redis_url: str,
    result_ttl: int = 300,
    timeout: int = 5,
) -> int:
    """
    Synchronous wrapper for run_single_task.

    Returns exit code: 0 = task executed, 1 = no task, 2 = error
    """
    try:
        had_task = asyncio.run(run_single_task(
            profile=profile,
            redis_url=redis_url,
            result_ttl=result_ttl,
            timeout=timeout,
        ))
        return 0 if had_task else 1
    except Exception as e:
        log.error(f"Runner error: {e}")
        return 2
