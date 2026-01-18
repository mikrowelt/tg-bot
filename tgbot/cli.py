#!/usr/bin/env python3
"""
Telegram Bot CLI

Usage:
    tg-bot health-check [options]
    tg-bot get-profile [options]
    tg-bot profile-health-check [options]
    tg-bot change-profile [options]
    tg-bot join-channel <channel> [options]
    tg-bot send-message <target> <text> [options]
    tg-bot check-ban <target> [options]
    tg-bot check-all-bans <channels>... [options]
    tg-bot worker --profiles <profiles> [options]
    tg-bot run-task --profile <profile> [options]
    tg-bot listen [options]
"""
import argparse
import asyncio
import os
import sys

from .commands import (
    change_profile,
    check_all_bans,
    check_ban,
    get_profile,
    health_check,
    join_channel,
    profile_health_check,
    send_message,
)


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tg-bot",
        description="Telegram Bot CLI for channel management and messaging",
    )
    parser.add_argument(
        "--profile", "-p",
        help="Profile name (defaults to PROFILE_NAME env var or 'profile')",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # health-check command
    subparsers.add_parser(
        "health-check",
        help="Check if the client is healthy and ready to send messages",
    )

    # get-profile command
    get_profile_parser = subparsers.add_parser(
        "get-profile",
        help="Get current Telegram profile information",
    )
    get_profile_parser.add_argument(
        "--include-photo",
        action="store_true",
        help="Include base64-encoded profile photo in response",
    )

    # profile-health-check command
    profile_health_parser = subparsers.add_parser(
        "profile-health-check",
        help="Check if profile is healthy and in sync with expected values",
    )
    profile_health_parser.add_argument(
        "--expected-first-name",
        help="Expected first name to verify against",
    )
    profile_health_parser.add_argument(
        "--expected-last-name",
        help="Expected last name to verify against",
    )
    profile_health_parser.add_argument(
        "--expected-username",
        help="Expected username to verify against",
    )
    profile_health_parser.add_argument(
        "--expected-about",
        help="Expected bio/about to verify against",
    )

    # change-profile command
    profile_parser = subparsers.add_parser(
        "change-profile",
        help="Update Telegram profile information",
    )
    profile_parser.add_argument(
        "--first-name", "-f",
        help="New first name",
    )
    profile_parser.add_argument(
        "--last-name", "-l",
        help="New last name",
    )
    profile_parser.add_argument(
        "--about", "-a",
        help="New bio/about text",
    )
    profile_parser.add_argument(
        "--username", "-u",
        help="New username (without @)",
    )
    profile_parser.add_argument(
        "--photo",
        help="Path to new profile photo",
    )

    # join-channel command
    join_parser = subparsers.add_parser(
        "join-channel",
        help="Join a channel and pass bot verification",
    )
    join_parser.add_argument(
        "channel",
        help="Channel link (https://t.me/... or @username)",
    )
    join_parser.add_argument(
        "--skip-verification", "-s",
        action="store_true",
        help="Skip bot verification after joining",
    )

    # send-message command
    msg_parser = subparsers.add_parser(
        "send-message",
        help="Send a message to a group, channel, or user",
    )
    msg_parser.add_argument(
        "target",
        help="Target chat (@username, channel ID, or link)",
    )
    msg_parser.add_argument(
        "text",
        help="Message text to send",
    )
    msg_parser.add_argument(
        "--comment-to", "-c",
        type=int,
        help="Post ID to comment on (for channel comments)",
    )
    msg_parser.add_argument(
        "--reply-to", "-r",
        type=int,
        help="Message ID to reply to",
    )

    # check-ban command
    ban_parser = subparsers.add_parser(
        "check-ban",
        help="Check if account is banned from a channel/group",
    )
    ban_parser.add_argument(
        "target",
        help="Target chat (@username, channel ID, or link)",
    )
    ban_parser.add_argument(
        "--test-message", "-t",
        action="store_true",
        help="Send a test message to verify write access (will be deleted)",
    )

    # check-all-bans command
    all_bans_parser = subparsers.add_parser(
        "check-all-bans",
        help="Check ban status across multiple channels",
    )
    all_bans_parser.add_argument(
        "channels",
        nargs="+",
        help="Channel targets (@username, channel ID, or link)",
    )
    all_bans_parser.add_argument(
        "--no-test-message",
        action="store_true",
        help="Skip test messages (only check membership, not write access)",
    )

    # worker command (dispatcher)
    worker_parser = subparsers.add_parser(
        "worker",
        help="Run dispatcher to watch Redis and spawn workers on-demand",
    )
    worker_parser.add_argument(
        "--profiles",
        help="Comma-separated list of profile names to handle",
    )
    worker_parser.add_argument(
        "--all",
        action="store_true",
        help="Handle all profiles found in BASE_DIR",
    )
    worker_parser.add_argument(
        "--redis",
        default=os.getenv("REDIS_URL", "redis://localhost:6379"),
        help="Redis URL (default: REDIS_URL env var or redis://localhost:6379)",
    )
    worker_parser.add_argument(
        "--result-ttl",
        type=int,
        default=int(os.getenv("RESULT_TTL", "300")),
        help="Seconds to keep results in Redis (default: 300)",
    )

    # run-task command (single task executor, used by dispatcher)
    task_parser = subparsers.add_parser(
        "run-task",
        help="Execute a single task from Redis queue (internal use)",
    )
    task_parser.add_argument(
        "--profile",
        required=True,
        help="Profile name to use",
    )
    task_parser.add_argument(
        "--redis",
        default=os.getenv("REDIS_URL", "redis://localhost:6379"),
        help="Redis URL",
    )
    task_parser.add_argument(
        "--result-ttl",
        type=int,
        default=int(os.getenv("RESULT_TTL", "300")),
        help="Seconds to keep results in Redis",
    )
    task_parser.add_argument(
        "--timeout",
        type=int,
        default=5,
        help="Seconds to wait for a task (default: 5)",
    )

    # listen command
    listen_parser = subparsers.add_parser(
        "listen",
        help="Listen to messages in groups and publish to Redis stream",
    )
    listen_parser.add_argument(
        "--groups",
        help="Comma-separated list of group IDs to listen to (listens to all if not specified)",
    )
    listen_parser.add_argument(
        "--listener-id",
        help="Unique listener ID (auto-generated if not specified)",
    )
    listen_parser.add_argument(
        "--account-id",
        type=int,
        help="Account ID in database (for heartbeat tracking)",
    )
    listen_parser.add_argument(
        "--redis",
        default=os.getenv("REDIS_URL", "redis://localhost:6379"),
        help="Redis URL (default: REDIS_URL env var or redis://localhost:6379)",
    )
    listen_parser.add_argument(
        "--heartbeat-interval",
        type=int,
        default=10,
        help="Heartbeat interval in seconds (default: 10)",
    )
    listen_parser.add_argument(
        "--debug",
        action="store_true",
        help="Print messages to stdout for debugging",
    )

    return parser


def main() -> None:
    parser = create_parser()
    args = parser.parse_args()

    if args.command == "health-check":
        result = health_check(profile=args.profile)
        sys.exit(0 if result and result.get("ok") else 1)

    elif args.command == "get-profile":
        result = get_profile(
            profile=args.profile,
            include_photo=args.include_photo,
        )
        sys.exit(0 if result else 1)

    elif args.command == "profile-health-check":
        result = profile_health_check(
            profile=args.profile,
            expected_first_name=args.expected_first_name,
            expected_last_name=args.expected_last_name,
            expected_username=args.expected_username,
            expected_about=args.expected_about,
        )
        sys.exit(0 if result and result.get("ok") else 1)

    elif args.command == "change-profile":
        # Check if at least one option is provided
        if not any([args.first_name, args.last_name, args.about, args.username, args.photo]):
            print("Error: At least one profile option is required", file=sys.stderr)
            parser.parse_args(["change-profile", "--help"])
            sys.exit(1)

        change_profile(
            profile=args.profile,
            first_name=args.first_name,
            last_name=args.last_name,
            about=args.about,
            username=args.username,
            photo=args.photo,
        )

    elif args.command == "join-channel":
        join_channel(
            channel=args.channel,
            profile=args.profile,
            skip_verification=args.skip_verification,
        )

    elif args.command == "send-message":
        result = send_message(
            target=args.target,
            text=args.text,
            profile=args.profile,
            comment_to=args.comment_to,
            reply_to=args.reply_to,
        )
        sys.exit(0 if result and result.ok else 1)

    elif args.command == "check-ban":
        result = check_ban(
            target=args.target,
            profile=args.profile,
            test_message=args.test_message,
        )
        # Exit 0 if not banned, 1 if banned or error
        if result:
            sys.exit(1 if result.get("is_banned") else 0)
        sys.exit(1)

    elif args.command == "check-all-bans":
        result = check_all_bans(
            channels=args.channels,
            profile=args.profile,
            test_message=not args.no_test_message,
        )
        # Exit 0 if no bans, 1 if any bans or error
        if result:
            sys.exit(1 if result.get("banned_count", 0) > 0 else 0)
        sys.exit(1)

    elif args.command == "worker":
        from .worker import run_dispatcher, discover_profiles

        # Determine profiles to handle
        if args.all:
            profiles = discover_profiles()
            if not profiles:
                print("Error: No profiles found in BASE_DIR", file=sys.stderr)
                sys.exit(1)
        elif args.profiles:
            profiles = [p.strip() for p in args.profiles.split(",")]
        else:
            print("Error: Either --profiles or --all is required", file=sys.stderr)
            parser.parse_args(["worker", "--help"])
            sys.exit(1)

        try:
            asyncio.run(run_dispatcher(
                profiles=profiles,
                redis_url=args.redis,
                result_ttl=args.result_ttl,
            ))
        except KeyboardInterrupt:
            pass
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "run-task":
        from .worker import run_task_sync

        exit_code = run_task_sync(
            profile=args.profile,
            redis_url=args.redis,
            result_ttl=args.result_ttl,
            timeout=args.timeout,
        )
        sys.exit(exit_code)

    elif args.command == "listen":
        from .listener import Listener, MessageStream, HeartbeatManager
        from .utils.config import Config

        # Load config
        config = Config.load(args.profile)

        # Initialize Redis connections
        message_stream = MessageStream(args.redis)
        heartbeat_manager = HeartbeatManager(args.redis)

        # Parse groups if specified
        group_ids = []
        if args.groups:
            group_ids = [int(g.strip()) for g in args.groups.split(",")]

        # Optional debug callback
        def debug_callback(msg):
            if args.debug:
                print(f"[{msg.listener_id}] {msg.discussion_group_id}: @{msg.sender_username}: {msg.text[:100]}")

        # Create listener
        listener = Listener(
            config=config,
            message_stream=message_stream,
            heartbeat_manager=heartbeat_manager,
            listener_id=args.listener_id,
            account_id=args.account_id,
            heartbeat_interval=args.heartbeat_interval,
            on_message=debug_callback if args.debug else None,
        )

        if group_ids:
            listener.assign_groups(group_ids)

        try:
            print(f"Starting listener {listener.listener_id} for profile {listener.profile_name}...")
            asyncio.run(listener.run_with_signal_handling())
        except KeyboardInterrupt:
            print("\nListener stopped")
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        finally:
            message_stream.close()
            heartbeat_manager.close()


if __name__ == "__main__":
    main()
