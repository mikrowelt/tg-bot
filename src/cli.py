#!/usr/bin/env python3
"""
Telegram Bot CLI

Usage:
    tg-bot change-profile [options]
    tg-bot join-channel <channel> [options]
    tg-bot send-message <target> <text> [options]
    tg-bot worker --profiles <profiles> [options]
    tg-bot run-task --profile <profile> [options]
"""
import argparse
import asyncio
import os
import sys

from .commands import change_profile, join_channel, send_message


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

    return parser


def main() -> None:
    parser = create_parser()
    args = parser.parse_args()

    if args.command == "change-profile":
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
        send_message(
            target=args.target,
            text=args.text,
            profile=args.profile,
            comment_to=args.comment_to,
            reply_to=args.reply_to,
        )

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


if __name__ == "__main__":
    main()
