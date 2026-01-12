from dataclasses import asdict
from typing import Any

from ..client import TgBot, JoinChannelError, ProfileUpdateError
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
    """Handle send_message command. Returns SendResult as dict."""
    target = args.get("target")
    text = args.get("text")

    if not target:
        raise ValueError("Missing required argument: target")
    if not text:
        raise ValueError("Missing required argument: text")

    comment_to = args.get("comment_to")
    reply_to = args.get("reply_to")

    if comment_to:
        result = await bot.send_comment(target, comment_to, text)
    else:
        result = await bot.send_message(target, text, reply_to=reply_to)

    return asdict(result)


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


async def handle_get_profile(bot: TgBot, args: dict[str, Any]) -> dict[str, Any]:
    """Handle get_profile command."""
    import base64

    result = await bot.get_profile()

    # Check if photo should be included
    include_photo = args.get("include_photo", False)

    if result.get("photo") is not None:
        if include_photo:
            # Base64 encode photo for JSON serialization
            result["photo"] = base64.b64encode(result["photo"]).decode("utf-8")
            result["photo_encoding"] = "base64"
        else:
            # Just indicate photo exists
            result["photo"] = True
            result["photo_encoding"] = None
    else:
        result["photo_encoding"] = None

    return result


async def handle_profile_health_check(bot: TgBot, args: dict[str, Any]) -> dict[str, Any]:
    """Handle profile_health_check command."""
    return await bot.profile_health_check(
        expected_first_name=args.get("expected_first_name"),
        expected_last_name=args.get("expected_last_name"),
        expected_username=args.get("expected_username"),
        expected_about=args.get("expected_about"),
    )


# Command handler mapping
HANDLERS = {
    Command.JOIN_CHANNEL: handle_join_channel,
    Command.SEND_MESSAGE: handle_send_message,
    Command.CHANGE_PROFILE: handle_change_profile,
    Command.GET_PROFILE: handle_get_profile,
    Command.PROFILE_HEALTH_CHECK: handle_profile_health_check,
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

    except ProfileUpdateError as e:
        log.error(f"Task {task.task_id} profile update error: {e}")
        return TaskResult.failure(task.task_id, str(e), "ProfileUpdateError")

    except Exception as e:
        log.error(f"Task {task.task_id} unexpected error: {e}")
        return TaskResult.failure(task.task_id, str(e), type(e).__name__)
