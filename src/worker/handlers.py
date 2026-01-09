from typing import Any

from ..client import TgBot, JoinChannelError, SendMessageError, ProfileUpdateError
from ..utils.logger import setup_logger
from .task import Task, TaskResult, Command

log = setup_logger("tg-bot.worker.handlers")


async def handle_join_channel(bot: TgBot, args: dict[str, Any]) -> dict[str, Any]:
    """Handle join_channel command."""
    channel = args.get("channel")
    if not channel:
        raise ValueError("Missing required argument: channel")

    skip_verification = args.get("skip_verification", False)

    channel_id = await bot.join_channel(
        channel_link=channel,
        verify=not skip_verification,
    )

    return {"channel_id": channel_id}


async def handle_send_message(bot: TgBot, args: dict[str, Any]) -> dict[str, Any]:
    """Handle send_message command."""
    target = args.get("target")
    text = args.get("text")

    if not target:
        raise ValueError("Missing required argument: target")
    if not text:
        raise ValueError("Missing required argument: text")

    comment_to = args.get("comment_to")
    reply_to = args.get("reply_to")

    if comment_to:
        await bot.send_comment(target, comment_to, text)
    else:
        await bot.send_message(target, text, reply_to=reply_to)

    return {"success": True}


async def handle_change_profile(bot: TgBot, args: dict[str, Any]) -> dict[str, Any]:
    """Handle change_profile command."""
    first_name = args.get("first_name")
    last_name = args.get("last_name")
    about = args.get("about")
    username = args.get("username")
    photo = args.get("photo")

    if not any([first_name, last_name, about, username, photo]):
        raise ValueError("At least one profile field must be provided")

    await bot.change_profile(
        first_name=first_name,
        last_name=last_name,
        about=about,
        username=username,
        photo_path=photo,
    )

    return {"success": True}


# Command handler mapping
HANDLERS = {
    Command.JOIN_CHANNEL: handle_join_channel,
    Command.SEND_MESSAGE: handle_send_message,
    Command.CHANGE_PROFILE: handle_change_profile,
}


async def execute_task(bot: TgBot, task: Task) -> TaskResult:
    """
    Execute a task and return the result.

    Args:
        bot: Connected TgBot instance
        task: Task to execute

    Returns:
        TaskResult with success or error
    """
    log.info(f"Executing task {task.task_id}: {task.command.value}")

    try:
        handler = HANDLERS.get(task.command)
        if not handler:
            raise ValueError(f"Unknown command: {task.command}")

        result = await handler(bot, task.args)
        log.info(f"Task {task.task_id} completed successfully")
        return TaskResult.success(task.task_id, result)

    except ValueError as e:
        log.error(f"Task {task.task_id} validation error: {e}")
        return TaskResult.failure(task.task_id, str(e), "ValidationError")

    except JoinChannelError as e:
        log.error(f"Task {task.task_id} join channel error: {e}")
        return TaskResult.failure(task.task_id, str(e), "JoinChannelError")

    except SendMessageError as e:
        log.error(f"Task {task.task_id} send message error: {e}")
        return TaskResult.failure(task.task_id, str(e), "SendMessageError")

    except ProfileUpdateError as e:
        log.error(f"Task {task.task_id} profile update error: {e}")
        return TaskResult.failure(task.task_id, str(e), "ProfileUpdateError")

    except Exception as e:
        log.error(f"Task {task.task_id} unexpected error: {e}")
        return TaskResult.failure(task.task_id, str(e), type(e).__name__)
