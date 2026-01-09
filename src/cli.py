#!/usr/bin/env python3
"""
Telegram Bot CLI

Usage:
    tg-bot change-profile [options]
    tg-bot join-channel <channel> [options]
    tg-bot send-message <target> <text> [options]
"""
import argparse
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


if __name__ == "__main__":
    main()
