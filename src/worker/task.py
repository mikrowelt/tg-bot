import json
from dataclasses import dataclass, field, asdict
from typing import Any
from enum import Enum


class Command(str, Enum):
    JOIN_CHANNEL = "join_channel"
    SEND_MESSAGE = "send_message"
    CHANGE_PROFILE = "change_profile"
    GET_PROFILE = "get_profile"
    PROFILE_HEALTH_CHECK = "profile_health_check"


class TaskStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"


@dataclass
class Task:
    """Represents a task to be executed by the worker."""
    task_id: str
    command: Command
    args: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json(cls, data: str | bytes) -> "Task":
        """Parse task from JSON string."""
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        parsed = json.loads(data)
        return cls(
            task_id=parsed["task_id"],
            command=Command(parsed["command"]),
            args=parsed.get("args", {}),
        )

    def to_json(self) -> str:
        """Serialize task to JSON string."""
        return json.dumps({
            "task_id": self.task_id,
            "command": self.command.value,
            "args": self.args,
        })


@dataclass
class TaskResult:
    """Result of a task execution."""
    task_id: str
    status: TaskStatus
    result: dict[str, Any] | None = None
    error: str | None = None
    error_type: str | None = None

    @classmethod
    def success(cls, task_id: str, result: dict[str, Any] | None = None) -> "TaskResult":
        """Create a success result."""
        return cls(
            task_id=task_id,
            status=TaskStatus.SUCCESS,
            result=result or {"success": True},
        )

    @classmethod
    def failure(cls, task_id: str, error: str, error_type: str | None = None) -> "TaskResult":
        """Create an error result."""
        return cls(
            task_id=task_id,
            status=TaskStatus.ERROR,
            error=error,
            error_type=error_type,
        )

    def to_json(self) -> str:
        """Serialize result to JSON string."""
        data = {
            "task_id": self.task_id,
            "status": self.status.value,
        }
        if self.result is not None:
            data["result"] = self.result
        if self.error is not None:
            data["error"] = self.error
        if self.error_type is not None:
            data["error_type"] = self.error_type
        return json.dumps(data)
