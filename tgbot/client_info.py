"""
Information retrieval mixin for TgBot.

This module provides info-related operations:
- get_target_type
- check_channel_membership
- get_latest_post
- get_recent_posts
- get_channel_info
- get_forum_topics
- get_recent_messages_in_topic
- get_available_reactions
"""
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.types import (
    Channel,
    Chat,
    ChatReactionsNone,
    ChatReactionsAll,
    ChatReactionsSome,
    ReactionEmoji,
)

from .utils.logger import setup_logger
from .utils.constants import DEFAULT_MESSAGE_LIMIT
from .client_profile import TgBotError

log = setup_logger("tg-bot.info")


class InfoMixin:
    """Mixin providing information retrieval operations for TgBot."""

    async def get_target_type(self, target: int | str) -> str:
        """
        Determine if a target is a channel, supergroup, or group.

        Returns:
            "channel" for broadcast channels (can only comment on posts)
            "supergroup" for supergroups (can send direct messages)
            "group" for basic groups (can send direct messages)
        """
        try:
            entity = await self.client.get_entity(target)

            if isinstance(entity, Channel):
                if entity.broadcast:
                    return "channel"
                else:
                    return "supergroup"
            elif isinstance(entity, Chat):
                return "group"
            else:
                return "unknown"

        except Exception as e:
            log.error(f"Failed to get target type: {e}")
            raise TgBotError(f"Failed to get target type: {e}")

    async def check_channel_membership(self, target: int | str) -> dict:
        """
        Check if the account is a member of a channel/group and get its type.

        This method handles private channels with invite links correctly by
        refreshing the dialogs cache if the initial lookup fails.

        Args:
            target: Channel username, ID, or invite link (t.me/+xxx)

        Returns:
            dict with:
                - is_member: bool
                - target_type: "channel" | "supergroup" | "group" | None
                - channel_id: int | None (the resolved channel ID)
                - error: str | None (error message if not a member)
        """
        result = {
            "is_member": False,
            "target_type": None,
            "channel_id": None,
            "error": None,
        }

        # First try direct entity lookup (works for public channels and cached entities)
        try:
            entity = await self.client.get_entity(target)

            if isinstance(entity, Channel):
                result["is_member"] = True
                result["channel_id"] = entity.id
                result["target_type"] = "channel" if entity.broadcast else "supergroup"
            elif isinstance(entity, Chat):
                result["is_member"] = True
                result["channel_id"] = entity.id
                result["target_type"] = "group"
            else:
                result["is_member"] = True
                result["channel_id"] = getattr(entity, 'id', None)
                result["target_type"] = "unknown"

            return result

        except Exception as e:
            error_msg = str(e).lower()
            if "not part of" not in error_msg and "cannot get entity" not in error_msg:
                # Some other error - not a membership issue
                result["error"] = str(e)
                return result

        # Direct lookup failed - refresh dialogs and try to find the channel
        log.info(f"Direct lookup failed for {target}, refreshing dialogs cache...")

        try:
            # Refresh dialogs to populate session cache
            async for dialog in self.client.iter_dialogs():
                entity = dialog.entity

                # Check if this is the target we're looking for
                if isinstance(entity, (Channel, Chat)):
                    # Match by ID if target is numeric
                    if isinstance(target, int) and entity.id == target:
                        result["is_member"] = True
                        result["channel_id"] = entity.id
                        if isinstance(entity, Channel):
                            result["target_type"] = "channel" if entity.broadcast else "supergroup"
                        else:
                            result["target_type"] = "group"
                        return result

                    # Match by username
                    if isinstance(target, str):
                        username = getattr(entity, 'username', None)
                        if username and target.lower().lstrip('@') == username.lower():
                            result["is_member"] = True
                            result["channel_id"] = entity.id
                            if isinstance(entity, Channel):
                                result["target_type"] = "channel" if entity.broadcast else "supergroup"
                            else:
                                result["target_type"] = "group"
                            return result

            # After refreshing dialogs, try get_entity again
            # (the entity should now be in the session cache)
            try:
                entity = await self.client.get_entity(target)

                if isinstance(entity, Channel):
                    result["is_member"] = True
                    result["channel_id"] = entity.id
                    result["target_type"] = "channel" if entity.broadcast else "supergroup"
                elif isinstance(entity, Chat):
                    result["is_member"] = True
                    result["channel_id"] = entity.id
                    result["target_type"] = "group"
                else:
                    result["is_member"] = True
                    result["channel_id"] = getattr(entity, 'id', None)
                    result["target_type"] = "unknown"

                return result

            except Exception as e2:
                log.warning(f"Still cannot resolve {target} after dialog refresh: {e2}")
                result["error"] = f"Not a member of target channel (checked via dialogs)"
                return result

        except Exception as e:
            log.error(f"Error refreshing dialogs: {e}")
            result["error"] = f"Cannot verify membership: {e}"
            return result

    async def get_latest_post(self, channel: int | str, with_comments: bool = True) -> dict | None:
        """
        Get the latest post from a broadcast channel.

        Args:
            channel: Channel username or ID
            with_comments: If True, only return posts that have comments enabled

        Returns:
            Dict with post info: {id, text, date, views, comments_enabled}
            or None if no suitable post found
        """
        log.info(f"Getting latest post from: {channel}")
        try:
            entity = await self.client.get_entity(channel)

            # Get recent messages from the channel
            async for message in self.client.iter_messages(entity, limit=10):
                # Skip service messages (joins, pins, etc.)
                if message.action is not None:
                    continue

                # Check if comments are enabled on this post
                comments_enabled = hasattr(message, 'replies') and message.replies is not None

                if with_comments and not comments_enabled:
                    continue

                return {
                    "id": message.id,
                    "text": message.text or "",
                    "date": message.date.isoformat() if message.date else None,
                    "views": getattr(message, 'views', None),
                    "comments_enabled": comments_enabled,
                }

            log.warning(f"No suitable post found in {channel}")
            return None

        except Exception as e:
            log.error(f"Failed to get latest post: {e}")
            raise TgBotError(f"Failed to get latest post: {e}")

    async def get_recent_posts(
        self,
        channel: int | str,
        limit: int = 10,
    ) -> list[dict]:
        """
        Get recent posts from a channel for warmup activities.

        Args:
            channel: Channel ID or username
            limit: Number of posts to fetch

        Returns:
            List of dicts with post info: [{id, text, date, views}, ...]
        """
        log.info(f"Getting {limit} recent posts from: {channel}")
        try:
            entity = await self.client.get_entity(channel)
            posts = []

            async for message in self.client.iter_messages(entity, limit=limit):
                # Skip service messages
                if message.action is not None:
                    continue

                posts.append({
                    "id": message.id,
                    "text": (message.text or "")[:200],
                    "date": message.date.isoformat() if message.date else None,
                    "views": getattr(message, 'views', None),
                })

            log.info(f"Found {len(posts)} posts in {channel}")
            return posts

        except Exception as e:
            log.error(f"Failed to get recent posts: {e}")
            raise TgBotError(f"Failed to get recent posts: {e}")

    async def get_forum_topics(
        self,
        channel: int | str,
        limit: int = 100,
    ) -> list[dict]:
        """
        Get forum topics from a supergroup with forum mode enabled.

        Args:
            channel: Supergroup ID or username
            limit: Maximum number of topics to fetch

        Returns:
            List of dicts with topic info:
            [
                {
                    "id": int,  # Topic ID (use as topic_id in send_message)
                    "title": str,
                    "icon_emoji_id": int | None,
                    "is_general": bool,  # True for the General topic
                    "is_closed": bool,
                    "is_hidden": bool,
                }
            ]

        Raises:
            TgBotError: If the target is not a forum supergroup
        """
        from telethon.tl.functions.channels import GetForumTopicsRequest

        log.info(f"Getting forum topics from: {channel}")
        try:
            entity = await self.client.get_entity(channel)

            # Verify it's a forum supergroup
            if not isinstance(entity, Channel) or entity.broadcast:
                raise TgBotError(f"Target {channel} is not a supergroup")
            if not getattr(entity, 'forum', False):
                raise TgBotError(f"Supergroup {channel} does not have forum mode enabled")

            # Get forum topics
            result = await self.client(GetForumTopicsRequest(
                channel=entity,
                offset_date=0,
                offset_id=0,
                offset_topic=0,
                limit=limit,
            ))

            topics = []
            for topic in result.topics:
                topics.append({
                    "id": topic.id,
                    "title": topic.title,
                    "icon_emoji_id": getattr(topic, 'icon_emoji_id', None),
                    "is_general": getattr(topic, 'short', False),  # General topic has 'short' flag
                    "is_closed": getattr(topic, 'closed', False),
                    "is_hidden": getattr(topic, 'hidden', False),
                })

            log.info(f"Found {len(topics)} forum topics in {channel}")
            return topics

        except TgBotError:
            raise
        except Exception as e:
            log.error(f"Failed to get forum topics: {e}")
            raise TgBotError(f"Failed to get forum topics: {e}")

    async def get_recent_messages_in_topic(
        self,
        channel: int | str,
        topic_id: int,
        limit: int = 10,
    ) -> list[dict]:
        """
        Get recent messages from a specific forum topic.

        Args:
            channel: Supergroup ID or username
            topic_id: Forum topic ID
            limit: Number of messages to fetch

        Returns:
            List of dicts with message info: [{id, text, date, sender_id, sender_username}, ...]
        """
        log.info(f"Getting {limit} recent messages from topic {topic_id} in {channel}")
        try:
            entity = await self.client.get_entity(channel)
            messages = []

            # Use reply_to parameter to filter messages in a specific topic
            async for message in self.client.iter_messages(entity, limit=limit, reply_to=topic_id):
                # Skip service messages
                if message.action is not None:
                    continue

                sender = await message.get_sender() if message.sender_id else None
                messages.append({
                    "id": message.id,
                    "text": (message.text or "")[:200],
                    "date": message.date.isoformat() if message.date else None,
                    "sender_id": message.sender_id,
                    "sender_username": getattr(sender, 'username', None) if sender else None,
                })

            log.info(f"Found {len(messages)} messages in topic {topic_id}")
            return messages

        except Exception as e:
            log.error(f"Failed to get messages from topic: {e}")
            raise TgBotError(f"Failed to get messages from topic: {e}")

    async def get_channel_info(
        self,
        channel: int | str,
        posts_limit: int = 10,
        text_length: int = 500,
    ) -> dict:
        """
        Get detailed information about a channel or group.

        Args:
            channel: Channel ID, username, or invite link
            posts_limit: Maximum number of recent posts to fetch (default 10)
            text_length: Maximum text length per post (default 500)

        Returns:
            {
                "id": int,
                "title": str,
                "username": str | None,
                "description": str | None,
                "member_count": int | None,
                "type": "channel" | "supergroup" | "group",
                "is_verified": bool,
                "is_scam": bool,
                "is_fake": bool,
                "recent_posts": [  # Only for broadcast channels
                    {
                        "id": int,
                        "text": str,
                        "date": str,
                        "views": int | None,
                    }
                ]
            }
        """
        log.info(f"Fetching channel info for: {channel} (posts_limit={posts_limit}, text_length={text_length})")

        try:
            # Get the entity
            entity = await self.client.get_entity(channel)

            result = {
                "id": entity.id,
                "title": getattr(entity, 'title', None),
                "username": getattr(entity, 'username', None),
                "description": None,
                "member_count": None,
                "type": "group",
                "is_verified": False,
                "is_scam": False,
                "is_fake": False,
                "recent_posts": [],
            }

            if isinstance(entity, Channel):
                result["type"] = "channel" if entity.broadcast else "supergroup"
                result["is_verified"] = getattr(entity, 'verified', False)
                result["is_scam"] = getattr(entity, 'scam', False)
                result["is_fake"] = getattr(entity, 'fake', False)
                # Check if supergroup has forum mode enabled (topics)
                result["is_forum"] = getattr(entity, 'forum', False) if not entity.broadcast else False

                # Get full channel info for description and member count
                try:
                    full_channel = await self.client(GetFullChannelRequest(entity))
                    result["description"] = getattr(full_channel.full_chat, 'about', None)
                    result["member_count"] = getattr(full_channel.full_chat, 'participants_count', None)
                    # Check if channel has linked discussion group (comments enabled)
                    linked_chat_id = getattr(full_channel.full_chat, 'linked_chat_id', None)
                    result["comments_enabled"] = linked_chat_id is not None
                    result["discussion_group_id"] = linked_chat_id
                except Exception as e:
                    log.warning(f"Could not get full channel info: {e}")
                    result["member_count"] = getattr(entity, 'participants_count', None)
                    result["comments_enabled"] = None  # Unknown
                    result["discussion_group_id"] = None

                # Get recent posts for broadcast channels
                if entity.broadcast:
                    try:
                        posts = []
                        async for message in self.client.iter_messages(entity, limit=posts_limit):
                            # Skip service messages
                            if message.action is not None:
                                continue
                            posts.append({
                                "id": message.id,
                                "text": (message.text or "")[:text_length],  # Truncate long texts
                                "date": message.date.isoformat() if message.date else None,
                                "views": getattr(message, 'views', None),
                            })
                        result["recent_posts"] = posts
                    except Exception as e:
                        log.warning(f"Could not fetch recent posts: {e}")

            elif isinstance(entity, Chat):
                result["type"] = "group"
                result["member_count"] = getattr(entity, 'participants_count', None)

            log.info(f"Got channel info: {result['title']} ({result['type']}, {result['member_count']} members)")
            return result

        except Exception as e:
            log.error(f"Failed to get channel info: {e}")
            raise TgBotError(f"Failed to get channel info: {e}")

    async def get_available_reactions(self, channel: int | str) -> list[str] | None:
        """
        Get available reactions for a channel or group.

        Args:
            channel: Channel ID, username, or invite link

        Returns:
            None - All emoji reactions are allowed (ChatReactionsAll)
            [] - No reactions allowed (ChatReactionsNone)
            ["👍", "❤️", ...] - Only these specific emoji allowed (ChatReactionsSome)

        Raises:
            TgBotError: If unable to get reaction information
        """
        log.info(f"Getting available reactions for: {channel}")

        try:
            entity = await self.client.get_entity(channel)
            full_channel = await self.client(GetFullChannelRequest(entity))
            available_reactions = full_channel.full_chat.available_reactions

            if isinstance(available_reactions, ChatReactionsNone):
                log.info(f"Channel {channel}: no reactions allowed")
                return []
            elif isinstance(available_reactions, ChatReactionsAll):
                log.info(f"Channel {channel}: all reactions allowed")
                return None
            elif isinstance(available_reactions, ChatReactionsSome):
                emojis = [
                    r.emoticon
                    for r in available_reactions.reactions
                    if isinstance(r, ReactionEmoji)
                ]
                log.info(f"Channel {channel}: specific reactions allowed: {emojis}")
                return emojis
            else:
                # Unknown type, assume all reactions allowed
                log.warning(f"Unknown reaction type for {channel}: {type(available_reactions)}")
                return None

        except Exception as e:
            log.error(f"Failed to get available reactions: {e}")
            raise TgBotError(f"Failed to get available reactions: {e}")
