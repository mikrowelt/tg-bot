"""Chat info command - get information about a chat/channel/group."""

import json
from ..utils.config import Config
from ..utils.logger import setup_logger
from ..client import TgBot
from .base import run_command

log = setup_logger("tg-bot.cmd.chat_info")


async def _get_chat_info(
    target: str,
    profile: str | None,
    include_topics: bool = False,
    include_posts: bool = False,
) -> dict:
    """
    Internal async implementation.

    Args:
        target: Chat/channel/group identifier (@username, ID, or link)
        profile: Profile name
        include_topics: Include forum topics (for forum supergroups)
        include_posts: Include recent posts/messages

    Returns:
        Dict with chat information
    """
    config = Config.load(profile)

    async with TgBot(config) as bot:
        # Get basic chat info
        info = await bot.get_channel_info(
            target,
            posts_limit=10 if include_posts else 0,
        )

        # Get chat type
        chat_type = await bot.get_target_type(target)
        info["chat_type_detected"] = chat_type

        # Get forum topics if requested and this is a forum supergroup
        if include_topics and info.get("is_forum"):
            try:
                topics = await bot.get_forum_topics(target)
                info["forum_topics"] = topics
            except Exception as e:
                info["forum_topics_error"] = str(e)

        return info


def get_chat_info(
    target: str,
    profile: str | None = None,
    include_topics: bool = False,
    include_posts: bool = False,
) -> dict | None:
    """
    Get information about a chat/channel/group.

    Args:
        target: Chat/channel/group identifier (@username, ID, or link)
        profile: Profile name (defaults to PROFILE_NAME env var or "profile")
        include_topics: Include forum topics (for forum supergroups)
        include_posts: Include recent posts/messages

    Returns:
        Dict with chat info:
        {
            "id": int,
            "title": str,
            "username": str | None,
            "description": str | None,
            "member_count": int | None,
            "type": "channel" | "supergroup" | "group",
            "chat_type_detected": str,
            "is_verified": bool,
            "is_scam": bool,
            "is_fake": bool,
            "is_forum": bool,  # True if forum mode enabled
            "comments_enabled": bool | None,
            "discussion_group_id": int | None,
            "recent_posts": list[dict],  # If include_posts=True
            "forum_topics": list[dict],  # If include_topics=True and is_forum
        }
    """
    return run_command(_get_chat_info)(
        target=target,
        profile=profile,
        include_topics=include_topics,
        include_posts=include_posts,
    )


def print_chat_info(info: dict) -> None:
    """Pretty print chat info."""
    if not info:
        print("No info available")
        return

    print(f"\n=== Chat Info ===")
    print(f"ID: {info.get('id')}")
    print(f"Title: {info.get('title')}")
    print(f"Username: @{info.get('username')}" if info.get('username') else "Username: None")
    print(f"Type: {info.get('type')} (detected: {info.get('chat_type_detected')})")
    print(f"Members: {info.get('member_count')}")
    print(f"Description: {(info.get('description') or '')[:100]}...")

    print(f"\n--- Flags ---")
    print(f"Is Forum: {info.get('is_forum', False)}")
    print(f"Is Verified: {info.get('is_verified', False)}")
    print(f"Is Scam: {info.get('is_scam', False)}")
    print(f"Is Fake: {info.get('is_fake', False)}")
    print(f"Comments Enabled: {info.get('comments_enabled')}")
    print(f"Discussion Group ID: {info.get('discussion_group_id')}")

    if info.get('forum_topics'):
        print(f"\n--- Forum Topics ({len(info['forum_topics'])}) ---")
        for topic in info['forum_topics']:
            flags = []
            if topic.get('is_general'):
                flags.append('GENERAL')
            if topic.get('is_closed'):
                flags.append('CLOSED')
            if topic.get('is_hidden'):
                flags.append('HIDDEN')
            flags_str = f" [{', '.join(flags)}]" if flags else ""
            print(f"  - [{topic['id']}] {topic['title']}{flags_str}")

    if info.get('recent_posts'):
        print(f"\n--- Recent Posts ({len(info['recent_posts'])}) ---")
        for post in info['recent_posts'][:5]:
            text = (post.get('text') or '')[:50].replace('\n', ' ')
            print(f"  - [{post['id']}] {text}...")

    print()
