"""
Telegram bot client wrapper.

This module provides the TgBot class for interacting with Telegram.
Operations are organized into mixins:
- ProfileMixin: Profile operations (from client_profile.py)
- ChannelsMixin: Channel join/leave operations (from client_channels.py)
- MessagesMixin: Message sending operations (from client_messages.py)
- InfoMixin: Information retrieval (from client_info.py)
"""
import asyncio
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.tl.functions.account import GetAuthorizationsRequest, ResetAuthorizationRequest

from .utils.config import Config
from .utils.logger import setup_logger
from .verification import ButtonVerification

# Import mixins
from .client_profile import ProfileMixin, TgBotError, ProfileUpdateError
from .client_channels import ChannelsMixin
from .client_messages import MessagesMixin, SendResult
from .client_info import InfoMixin

# Import AI verification (optional - may not be available if anthropic not installed)
try:
    from .verification import AIVerificationAgent, VerificationResult
    AI_VERIFICATION_AVAILABLE = True
except ImportError:
    AI_VERIFICATION_AVAILABLE = False
    AIVerificationAgent = None
    VerificationResult = None

log = setup_logger("tg-bot.client")


class JoinChannelError(TgBotError):
    """Raised when joining a channel fails."""
    pass


class SendMessageError(TgBotError):
    """Raised when sending a message fails."""
    pass


class TgBot(ProfileMixin, ChannelsMixin, MessagesMixin, InfoMixin):
    """Telegram bot client wrapper.

    Inherits operations from mixins:

    ProfileMixin (client_profile.py):
    - change_profile
    - set_username
    - get_profile
    - profile_health_check
    - delete_all_profile_photos
    - upload_multiple_photos
    - get_joined_channels
    - get_profile_photos

    ChannelsMixin (client_channels.py):
    - join_channel
    - leave_channel

    MessagesMixin (client_messages.py):
    - send_message
    - send_comment
    - verify_in_comments
    - send_reaction

    InfoMixin (client_info.py):
    - get_target_type
    - check_channel_membership
    - get_latest_post
    - get_recent_posts
    - get_channel_info
    - get_forum_topics
    - get_recent_messages_in_topic
    """

    def __init__(self, config: Config, anthropic_api_key: str | None = None):
        self.config = config
        self.anthropic_api_key = anthropic_api_key
        self._client: TelegramClient | None = None
        self._verification: ButtonVerification | None = None
        self._ai_verification: "AIVerificationAgent | None" = None

    @property
    def client(self) -> TelegramClient:
        if self._client is None:
            raise TgBotError("Client not initialized. Call connect() first.")
        return self._client

    @property
    def verification(self) -> ButtonVerification:
        if self._verification is None:
            self._verification = ButtonVerification(
                self.client, self.config.captcha_api_key
            )
        return self._verification

    @property
    def ai_verification(self) -> "AIVerificationAgent | None":
        """Get AI verification agent (lazy initialization)."""
        if not AI_VERIFICATION_AVAILABLE:
            return None

        if self._ai_verification is None and self.anthropic_api_key:
            self._ai_verification = AIVerificationAgent(
                self.client,
                api_key=self.anthropic_api_key,
            )

        return self._ai_verification

    async def connect(self) -> None:
        """Connect to Telegram and authenticate."""
        log.info("Connecting to Telegram...")
        proxy = self.config.proxy.to_tuple() if self.config.proxy else None

        if proxy:
            log.debug(f"Using proxy: {self.config.proxy}")

        self._client = TelegramClient(
            str(self.config.session_path),
            self.config.app_id,
            self.config.app_hash,
            proxy=proxy,
            device_model=self.config.device,
            system_version=self.config.sdk,
            app_version=self.config.app_version,
            lang_code=self.config.lang_pack,
        )

        await self._client.connect()
        log.debug("TCP connection established")

        if not await self._client.is_user_authorized():
            log.info("Authorization required")
            phone = "+" + self.config.phone
            await self._client.send_code_request(phone)
            log.info(f"Code sent to {phone}")
            try:
                code = input("Enter the code you received: ")
                await self._client.sign_in(phone, code)
                log.info("Signed in with code")
            except SessionPasswordNeededError:
                if not self.config.two_fa:
                    log.error("2FA required but not configured")
                    raise TgBotError("2FA required but not configured in profile")
                await self._client.sign_in(password=self.config.two_fa)
                log.info("Signed in with 2FA")

        me = await self._client.get_me()
        log.info(f"Connected as: {me.first_name} (@{me.username or 'no username'})")

    async def disconnect(self) -> None:
        """Disconnect from Telegram."""
        if self._client:
            await self._client.disconnect()
            self._client = None
            self._verification = None
            log.info("Disconnected from Telegram")

    async def __aenter__(self) -> "TgBot":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.disconnect()

    # ============ HEALTH CHECK ============

    async def health_check(self) -> dict:
        """
        Check if the client is healthy and ready to send messages.

        Returns a dict with:
            - ok: bool - True if all checks pass
            - connected: bool - TCP connection status
            - authorized: bool - User authorization status
            - user_id: int | None - Current user ID
            - username: str | None - Current username
            - restricted: bool - Whether account has restrictions
            - error: str | None - Error message if any check fails
        """
        result = {
            "ok": False,
            "connected": False,
            "authorized": False,
            "user_id": None,
            "username": None,
            "restricted": False,
            "error": None,
        }

        try:
            # Check connection
            if self._client is None:
                result["error"] = "Client not initialized"
                return result

            if not self._client.is_connected():
                result["error"] = "Not connected to Telegram"
                return result
            result["connected"] = True

            # Check authorization
            if not await self._client.is_user_authorized():
                result["error"] = "Not authorized"
                return result
            result["authorized"] = True

            # Get user info
            me = await self._client.get_me()
            result["user_id"] = me.id
            result["username"] = me.username

            # Check for restrictions
            if me.restricted:
                result["restricted"] = True
                reason = me.restriction_reason if me.restriction_reason else "unknown"
                result["error"] = f"Account is restricted: {reason}"
                return result

            # All checks passed
            result["ok"] = True
            log.info(f"Health check passed for user {me.id}")

        except Exception as e:
            log.error(f"Health check failed: {e}")
            result["error"] = str(e)

        return result

    async def terminate_other_sessions(self) -> dict:
        """
        Terminate all other sessions except the current one.

        Returns:
            {
                "terminated": int - Number of sessions terminated
                "current_session_hash": int - Hash of the current session (kept)
            }
        """
        log.info("Terminating other sessions...")

        try:
            # Get all authorizations
            auths = await self.client(GetAuthorizationsRequest())

            terminated = 0
            current_hash = None

            for auth in auths.authorizations:
                if auth.current:
                    current_hash = auth.hash
                    log.debug(f"Keeping current session: {auth.app_name} ({auth.device_model})")
                    continue

                # Terminate this session
                log.debug(f"Terminating session: {auth.app_name} ({auth.device_model})")
                try:
                    await self.client(ResetAuthorizationRequest(hash=auth.hash))
                    terminated += 1
                except Exception as e:
                    log.warning(f"Failed to terminate session {auth.hash}: {e}")

            log.info(f"Terminated {terminated} other sessions")
            return {
                "terminated": terminated,
                "current_session_hash": current_hash,
            }

        except Exception as e:
            log.error(f"Failed to terminate sessions: {e}")
            raise TgBotError(f"Failed to terminate sessions: {e}")
