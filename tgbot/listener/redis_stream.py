"""Redis utilities for message streaming and heartbeats."""

import json
import logging
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional

import redis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


@dataclass
class ChannelMessage:
    """Message received from a channel/group."""

    channel_id: int
    message_id: int
    text: str
    sender_id: int | None
    sender_username: str | None
    message_date: str  # ISO format
    has_media: bool
    media_type: str | None
    reply_to_msg_id: int | None  # For comments, the post being commented on
    discussion_group_id: int | None  # If this is a comment in a discussion group
    listener_id: str | None = None  # ID of the listener that received this

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ChannelMessage":
        return cls(**data)


class MessageStream:
    """Redis stream for channel messages."""

    STREAM_KEY = "tg:listener:messages"
    CONSUMER_GROUP = "analyzers"
    MAX_LEN = 1_000_000  # Max messages in stream

    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or REDIS_URL
        self._redis: Optional[redis.Redis] = None

    @property
    def redis(self) -> redis.Redis:
        if self._redis is None:
            self._redis = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5,
            )
        return self._redis

    def close(self):
        """Close Redis connection."""
        if self._redis:
            self._redis.close()
            self._redis = None

    def ensure_consumer_group(self):
        """Create consumer group if it doesn't exist."""
        try:
            self.redis.xgroup_create(
                self.STREAM_KEY,
                self.CONSUMER_GROUP,
                id="0",
                mkstream=True,
            )
            logger.info(f"Created consumer group: {self.CONSUMER_GROUP}")
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise
            # Group already exists, that's fine

    def publish(self, message: ChannelMessage) -> str:
        """
        Publish a message to the stream.

        Returns the message ID in the stream.
        """
        data = {
            k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) if v is not None else ""
            for k, v in message.to_dict().items()
        }

        msg_id = self.redis.xadd(
            self.STREAM_KEY,
            data,
            maxlen=self.MAX_LEN,
            approximate=True,
        )

        logger.debug(f"Published message {message.message_id} from channel {message.channel_id}")
        return msg_id

    def get_stream_length(self) -> int:
        """Get total messages in the stream."""
        return self.redis.xlen(self.STREAM_KEY)

    def get_recent_messages(self, count: int = 50) -> list[dict]:
        """Get recent messages from stream (for debug UI)."""
        try:
            # Use XREVRANGE to get most recent messages
            result = self.redis.xrevrange(self.STREAM_KEY, count=count)
            messages = []
            for msg_id, data in result:
                parsed = {
                    "stream_id": msg_id,
                    "channel_id": int(data.get("channel_id", 0)),
                    "message_id": int(data.get("message_id", 0)),
                    "text": data.get("text", ""),
                    "sender_id": int(data["sender_id"]) if data.get("sender_id") else None,
                    "sender_username": data.get("sender_username") or None,
                    "message_date": data.get("message_date", ""),
                    "has_media": data.get("has_media", "").lower() == "true",
                    "media_type": data.get("media_type") or None,
                    "reply_to_msg_id": int(data["reply_to_msg_id"]) if data.get("reply_to_msg_id") else None,
                    "discussion_group_id": int(data["discussion_group_id"]) if data.get("discussion_group_id") else None,
                    "listener_id": data.get("listener_id") or None,
                }
                messages.append(parsed)
            return messages
        except Exception as e:
            logger.error(f"Failed to get recent messages: {e}")
            return []


class HeartbeatManager:
    """Manage listener heartbeats in Redis."""

    HEARTBEAT_KEY_PREFIX = "tg:listener:heartbeat:"
    HEARTBEAT_TTL = 30  # Seconds before heartbeat expires

    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or REDIS_URL
        self._redis: Optional[redis.Redis] = None

    @property
    def redis(self) -> redis.Redis:
        if self._redis is None:
            self._redis = redis.from_url(
                self.redis_url,
                decode_responses=True,
            )
        return self._redis

    def close(self):
        if self._redis:
            self._redis.close()
            self._redis = None

    def send_heartbeat(
        self,
        listener_id: str,
        account_id: int,
        profile_name: str,
        channel_count: int,
        messages_received: int = 0,
        status: str = "listening",
        error: str | None = None,
    ):
        """Send a heartbeat for a listener."""
        key = f"{self.HEARTBEAT_KEY_PREFIX}{listener_id}"
        data = {
            "listener_id": listener_id,
            "account_id": str(account_id),
            "profile_name": profile_name,
            "channel_count": str(channel_count),
            "messages_received": str(messages_received),
            "status": status,
            "last_heartbeat": datetime.utcnow().isoformat(),
            "error": error or "",
        }
        self.redis.hset(key, mapping=data)
        self.redis.expire(key, self.HEARTBEAT_TTL)

    def get_heartbeat(self, listener_id: str) -> dict | None:
        """Get heartbeat data for a listener."""
        key = f"{self.HEARTBEAT_KEY_PREFIX}{listener_id}"
        data = self.redis.hgetall(key)
        if data:
            # Convert numeric fields
            return {
                "listener_id": data.get("listener_id"),
                "account_id": int(data["account_id"]) if data.get("account_id") else None,
                "profile_name": data.get("profile_name"),
                "channel_count": int(data["channel_count"]) if data.get("channel_count") else 0,
                "messages_received": int(data["messages_received"]) if data.get("messages_received") else 0,
                "status": data.get("status"),
                "last_heartbeat": data.get("last_heartbeat"),
                "error": data.get("error") or None,
            }
        return None

    def get_all_heartbeats(self) -> list[dict]:
        """Get all active listener heartbeats."""
        pattern = f"{self.HEARTBEAT_KEY_PREFIX}*"
        heartbeats = []

        for key in self.redis.scan_iter(pattern):
            listener_id = key.replace(self.HEARTBEAT_KEY_PREFIX, "")
            data = self.get_heartbeat(listener_id)
            if data:
                heartbeats.append(data)

        return heartbeats

    def is_alive(self, listener_id: str) -> bool:
        """Check if a listener is alive (has recent heartbeat)."""
        key = f"{self.HEARTBEAT_KEY_PREFIX}{listener_id}"
        return self.redis.exists(key) > 0

    def remove_heartbeat(self, listener_id: str):
        """Remove a listener's heartbeat."""
        key = f"{self.HEARTBEAT_KEY_PREFIX}{listener_id}"
        self.redis.delete(key)


class RedisClient:
    """Unified Redis client for listener functionality."""

    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or REDIS_URL
        self.messages = MessageStream(redis_url)
        self.heartbeats = HeartbeatManager(redis_url)

    def close(self):
        """Close all Redis connections."""
        self.messages.close()
        self.heartbeats.close()
