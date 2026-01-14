"""
AI-powered verification agent using Claude to detect and solve verification challenges.
"""

import asyncio
import hashlib
import json
import re
import os
from dataclasses import dataclass, field
from typing import Any
from datetime import datetime

from telethon import TelegramClient
from telethon.tl.types import Message, User
from telethon.errors import FloodWaitError

from ..utils.logger import setup_logger

log = setup_logger("tg-bot.verification.ai_agent")

# Try to import anthropic, but don't fail if not installed
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    log.warning("anthropic package not installed, AI verification will be disabled")


@dataclass
class VerificationResult:
    """Result of a verification attempt."""
    success: bool
    action_taken: str | None = None
    error: str | None = None
    cached: bool = False
    details: dict = field(default_factory=dict)


@dataclass
class CachedAction:
    """Cached verification action."""
    action_type: str  # click_button, send_message, solve_math, etc.
    action_data: dict  # Parameters for the action
    success_count: int = 0
    fail_count: int = 0
    last_used: datetime = field(default_factory=datetime.utcnow)

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.fail_count
        return self.success_count / total if total > 0 else 0.0


class VerificationCache:
    """Cache for verification patterns and solutions."""

    def __init__(self):
        self._cache: dict[str, CachedAction] = {}

    def _normalize_text(self, text: str, our_username: str | None, our_first_name: str | None) -> str:
        """Normalize message text by replacing dynamic parts with placeholders."""
        if not text:
            return ""

        normalized = text.lower().strip()

        # Replace our username with placeholder
        if our_username:
            normalized = normalized.replace(f"@{our_username.lower()}", "{user}")
            normalized = normalized.replace(our_username.lower(), "{user}")

        # Replace our first name with placeholder
        if our_first_name:
            normalized = normalized.replace(our_first_name.lower(), "{name}")

        # Replace numbers (for math captchas)
        normalized = re.sub(r'\d+', '{num}', normalized)

        # Replace common random emojis
        emoji_pattern = re.compile(
            "["
            "\U0001F300-\U0001F9FF"  # Various symbols and pictographs
            "]+",
            flags=re.UNICODE
        )
        normalized = emoji_pattern.sub('{emoji}', normalized)

        # Normalize whitespace
        normalized = re.sub(r'\s+', ' ', normalized)

        return normalized

    def _create_fingerprint(
        self,
        bot_username: str,
        message_text: str,
        button_texts: list[str],
        our_username: str | None,
        our_first_name: str | None,
    ) -> str:
        """Create a unique fingerprint for a verification pattern."""
        normalized_text = self._normalize_text(message_text, our_username, our_first_name)

        # Normalize button texts too
        normalized_buttons = sorted([
            self._normalize_text(btn, our_username, our_first_name)
            for btn in button_texts
        ])

        fingerprint_data = {
            "bot": bot_username.lower() if bot_username else "unknown",
            "pattern": normalized_text,
            "buttons": normalized_buttons,
        }

        # Create hash
        fingerprint_str = json.dumps(fingerprint_data, sort_keys=True)
        return hashlib.sha256(fingerprint_str.encode()).hexdigest()[:16]

    def get(
        self,
        bot_username: str,
        message_text: str,
        button_texts: list[str],
        our_username: str | None = None,
        our_first_name: str | None = None,
    ) -> CachedAction | None:
        """Get cached action for a verification pattern."""
        fingerprint = self._create_fingerprint(
            bot_username, message_text, button_texts, our_username, our_first_name
        )

        cached = self._cache.get(fingerprint)
        if cached and cached.success_rate >= 0.5:  # Only use if success rate is acceptable
            log.debug(f"Cache hit for fingerprint {fingerprint} (success rate: {cached.success_rate:.0%})")
            return cached

        return None

    def set(
        self,
        bot_username: str,
        message_text: str,
        button_texts: list[str],
        action: CachedAction,
        our_username: str | None = None,
        our_first_name: str | None = None,
    ) -> None:
        """Cache an action for a verification pattern."""
        fingerprint = self._create_fingerprint(
            bot_username, message_text, button_texts, our_username, our_first_name
        )

        self._cache[fingerprint] = action
        log.debug(f"Cached action for fingerprint {fingerprint}: {action.action_type}")

    def record_result(
        self,
        bot_username: str,
        message_text: str,
        button_texts: list[str],
        success: bool,
        our_username: str | None = None,
        our_first_name: str | None = None,
    ) -> None:
        """Record success/failure for a cached pattern."""
        fingerprint = self._create_fingerprint(
            bot_username, message_text, button_texts, our_username, our_first_name
        )

        if fingerprint in self._cache:
            if success:
                self._cache[fingerprint].success_count += 1
            else:
                self._cache[fingerprint].fail_count += 1
            self._cache[fingerprint].last_used = datetime.utcnow()

    def export(self) -> dict:
        """Export cache for persistence."""
        return {
            fp: {
                "action_type": action.action_type,
                "action_data": action.action_data,
                "success_count": action.success_count,
                "fail_count": action.fail_count,
            }
            for fp, action in self._cache.items()
        }

    def load(self, data: dict) -> None:
        """Load cache from persisted data."""
        for fp, action_data in data.items():
            self._cache[fp] = CachedAction(
                action_type=action_data["action_type"],
                action_data=action_data["action_data"],
                success_count=action_data.get("success_count", 0),
                fail_count=action_data.get("fail_count", 0),
            )
        log.info(f"Loaded {len(self._cache)} cached verification patterns")


# Global cache instance
_verification_cache = VerificationCache()


def get_cache() -> VerificationCache:
    """Get the global verification cache."""
    return _verification_cache


class AIVerificationAgent:
    """
    AI-powered verification agent that uses Claude to detect and solve
    verification challenges in Telegram channels/groups.
    """

    SYSTEM_PROMPT = """You are a Telegram verification bypass agent. Your job is to analyze messages from bots and determine if they are verification challenges, and if so, how to solve them.

You will receive:
- Message text from a bot
- List of buttons (if any)
- Context about the situation

Your task:
1. Determine if this is a verification message
2. If yes, determine the type and solution
3. Return a JSON response with the action to take

Response format (JSON only, no other text):
{
    "is_verification": true/false,
    "verification_type": "button_click|math_captcha|emoji_select|text_reply|pm_verify|none",
    "action": {
        "type": "click_button|send_message|solve_math|send_to_bot|none",
        "button_text": "text of button to click (if click_button)",
        "button_index": 0,
        "message": "message to send (if send_message)",
        "math_expression": "expression to solve (if solve_math)",
        "bot_username": "@bot (if send_to_bot)",
        "bot_message": "message to send to bot (if send_to_bot)"
    },
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation"
}

Common verification patterns:
- "Click the button to verify" → click_button
- "Solve X+Y=" → solve_math
- "Select the [emoji]" → click_button with emoji
- "Send /start to @BotName" → send_to_bot
- "You must verify" + buttons → click_button (usually first/verify button)

Always respond with valid JSON only."""

    def __init__(
        self,
        client: TelegramClient,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-20250514",
        cache: VerificationCache | None = None,
    ):
        self.client = client
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model
        self.cache = cache or get_cache()

        if not ANTHROPIC_AVAILABLE:
            raise RuntimeError("anthropic package not installed. Run: pip install anthropic")

        if not self.api_key:
            raise ValueError("Anthropic API key not provided. Set ANTHROPIC_API_KEY env var or pass api_key parameter.")

        self.anthropic_client = anthropic.Anthropic(api_key=self.api_key)

        # Track our account info
        self._our_user_id: int | None = None
        self._our_username: str | None = None
        self._our_first_name: str | None = None

    async def _ensure_user_info(self) -> None:
        """Ensure we have our account info cached."""
        if self._our_user_id is None:
            me = await self.client.get_me()
            self._our_user_id = me.id
            self._our_username = me.username
            self._our_first_name = me.first_name

    def _is_message_for_us(self, message: Message, our_message_id: int | None = None) -> bool:
        """Check if a verification message is addressed to our account."""
        if not message.text:
            return False

        text_lower = message.text.lower()

        # Check if it's a private message (DM) - always for us
        if message.is_private:
            return True

        # Check if our username is mentioned
        if self._our_username and f"@{self._our_username.lower()}" in text_lower:
            return True

        # Check if our first name is mentioned
        if self._our_first_name and self._our_first_name.lower() in text_lower:
            return True

        # Check if it's a reply to our message
        if message.reply_to and our_message_id:
            if message.reply_to.reply_to_msg_id == our_message_id:
                return True

        # Check if message contains any @username - if not, might be broadcast
        if not re.search(r'@\w+', message.text):
            # No specific user mentioned, could be for everyone
            # Only handle if it has verification-like buttons
            if message.reply_markup and hasattr(message.reply_markup, 'rows'):
                return True

        return False

    def _extract_buttons(self, message: Message) -> list[dict]:
        """Extract button information from a message."""
        buttons = []

        if not message.reply_markup or not hasattr(message.reply_markup, 'rows'):
            return buttons

        for row_idx, row in enumerate(message.reply_markup.rows):
            for btn_idx, button in enumerate(row.buttons):
                button_info = {
                    "text": getattr(button, 'text', ''),
                    "row": row_idx,
                    "index": btn_idx,
                    "type": type(button).__name__,
                }

                # Check for URL buttons
                if hasattr(button, 'url') and button.url:
                    button_info["url"] = button.url

                buttons.append(button_info)

        return buttons

    async def _analyze_with_ai(self, message: Message, context: str = "") -> dict:
        """Use Claude to analyze a verification message."""
        buttons = self._extract_buttons(message)
        button_texts = [b["text"] for b in buttons]

        # Prepare the prompt
        user_prompt = f"""Analyze this bot message:

Bot username: @{message.sender.username if message.sender else 'unknown'}
Message text: {message.text or '[no text]'}
Buttons: {json.dumps(button_texts) if button_texts else '[no buttons]'}
Context: {context or 'User joined channel or sent first message'}

Is this a verification challenge? If so, how should we solve it?
Respond with JSON only."""

        try:
            response = self.anthropic_client.messages.create(
                model=self.model,
                max_tokens=500,
                system=self.SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )

            # Parse JSON response
            response_text = response.content[0].text.strip()

            # Try to extract JSON if wrapped in markdown
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]

            return json.loads(response_text)

        except json.JSONDecodeError as e:
            log.error(f"Failed to parse AI response as JSON: {e}")
            return {"is_verification": False, "error": "Invalid AI response"}
        except Exception as e:
            log.error(f"AI analysis failed: {e}")
            return {"is_verification": False, "error": str(e)}

    async def _execute_action(self, action: dict, message: Message) -> bool:
        """Execute a verification action."""
        action_type = action.get("type", "none")

        try:
            if action_type == "click_button":
                return await self._action_click_button(action, message)
            elif action_type == "send_message":
                return await self._action_send_message(action, message)
            elif action_type == "solve_math":
                return await self._action_solve_math(action, message)
            elif action_type == "send_to_bot":
                return await self._action_send_to_bot(action)
            elif action_type == "none":
                log.debug("No action needed")
                return True
            else:
                log.warning(f"Unknown action type: {action_type}")
                return False

        except FloodWaitError as e:
            log.warning(f"Rate limited during verification action: {e.seconds}s")
            await asyncio.sleep(e.seconds + 5)
            return False
        except Exception as e:
            log.error(f"Action execution failed: {e}")
            return False

    async def _action_click_button(self, action: dict, message: Message) -> bool:
        """Click a button on the message."""
        button_text = action.get("button_text", "")
        button_index = action.get("button_index", 0)

        buttons = self._extract_buttons(message)
        if not buttons:
            log.warning("No buttons to click")
            return False

        # Try to find button by text first
        target_button = None
        for btn in buttons:
            if button_text and button_text.lower() in btn["text"].lower():
                target_button = btn
                break

        # Fall back to index
        if not target_button and button_index < len(buttons):
            target_button = buttons[button_index]

        if not target_button:
            log.warning(f"Could not find button: text='{button_text}', index={button_index}")
            return False

        log.info(f"Clicking button: '{target_button['text']}'")

        await asyncio.sleep(1 + asyncio.get_event_loop().time() % 2)  # Random delay

        # Click the button
        await message.click(target_button["row"], target_button["index"])

        log.info("Button clicked successfully")
        return True

    async def _action_send_message(self, action: dict, message: Message) -> bool:
        """Send a message reply."""
        text = action.get("message", "")
        if not text:
            log.warning("No message text to send")
            return False

        log.info(f"Sending message: '{text[:50]}...'")

        await asyncio.sleep(1 + asyncio.get_event_loop().time() % 2)

        await self.client.send_message(
            message.chat_id,
            text,
            reply_to=message.id
        )

        return True

    async def _action_solve_math(self, action: dict, message: Message) -> bool:
        """Solve a math expression and send the answer."""
        expression = action.get("math_expression", "")

        if not expression:
            # Try to extract from message
            match = re.search(r'(\d+)\s*([+\-*/])\s*(\d+)', message.text or "")
            if match:
                expression = match.group(0)

        if not expression:
            log.warning("No math expression to solve")
            return False

        # Safely evaluate the expression
        try:
            # Only allow basic math operations
            allowed = set('0123456789+-*/ ()')
            if not all(c in allowed for c in expression):
                log.warning(f"Invalid characters in math expression: {expression}")
                return False

            result = eval(expression)
            log.info(f"Solved math: {expression} = {result}")

            await asyncio.sleep(1 + asyncio.get_event_loop().time() % 2)

            await self.client.send_message(
                message.chat_id,
                str(int(result)),
                reply_to=message.id
            )

            return True

        except Exception as e:
            log.error(f"Failed to solve math: {e}")
            return False

    async def _action_send_to_bot(self, action: dict) -> bool:
        """Send a message to a verification bot."""
        bot_username = action.get("bot_username", "")
        bot_message = action.get("bot_message", "/start")

        if not bot_username:
            log.warning("No bot username to message")
            return False

        # Clean up bot username
        bot_username = bot_username.lstrip("@")

        log.info(f"Sending '{bot_message}' to @{bot_username}")

        await asyncio.sleep(2 + asyncio.get_event_loop().time() % 3)

        try:
            await self.client.send_message(bot_username, bot_message)

            # Wait for response and handle it
            await asyncio.sleep(3)

            # Check for response from bot
            async for response in self.client.iter_messages(bot_username, limit=3):
                if response.sender and getattr(response.sender, 'bot', False):
                    # Recursively handle bot response
                    if response.reply_markup:
                        log.info("Bot responded with buttons, handling...")
                        return await self._action_click_button(
                            {"button_index": 0},  # Click first button
                            response
                        )

            return True

        except Exception as e:
            log.error(f"Failed to message bot: {e}")
            return False

    async def check_and_handle_verification(
        self,
        chat_id: int | str,
        our_message_id: int | None = None,
        context: str = "after_join",
        wait_seconds: float = 3.0,
    ) -> VerificationResult:
        """
        Check for verification messages and handle them.

        Args:
            chat_id: Channel/group to check
            our_message_id: ID of our message (to detect replies)
            context: "after_join" or "after_message"
            wait_seconds: How long to wait before checking

        Returns:
            VerificationResult with success status and details
        """
        await self._ensure_user_info()

        log.info(f"Checking for verification in {chat_id} ({context})")

        # Wait for verification bots to respond
        await asyncio.sleep(wait_seconds)

        # Get recent messages
        verification_message = None
        bot_username = None

        try:
            async for message in self.client.iter_messages(chat_id, limit=10):
                # Skip our own messages
                if message.sender_id == self._our_user_id:
                    continue

                # Check if sender is a bot
                sender = message.sender
                if not sender or not getattr(sender, 'bot', False):
                    continue

                # Check if message is for us
                if not self._is_message_for_us(message, our_message_id):
                    continue

                # Found a bot message for us
                verification_message = message
                bot_username = getattr(sender, 'username', 'unknown')
                log.info(f"Found potential verification from @{bot_username}")
                break

            if not verification_message:
                log.debug("No verification message found")
                return VerificationResult(success=True, action_taken=None)

            # Extract button texts for cache lookup
            buttons = self._extract_buttons(verification_message)
            button_texts = [b["text"] for b in buttons]

            # Check cache first
            cached_action = self.cache.get(
                bot_username or "unknown",
                verification_message.text or "",
                button_texts,
                self._our_username,
                self._our_first_name,
            )

            if cached_action:
                log.info(f"Using cached action: {cached_action.action_type}")
                success = await self._execute_action(
                    {"type": cached_action.action_type, **cached_action.action_data},
                    verification_message
                )

                # Record result
                self.cache.record_result(
                    bot_username or "unknown",
                    verification_message.text or "",
                    button_texts,
                    success,
                    self._our_username,
                    self._our_first_name,
                )

                return VerificationResult(
                    success=success,
                    action_taken=cached_action.action_type,
                    cached=True,
                    details={"bot": bot_username}
                )

            # Use AI to analyze
            log.info("Using AI to analyze verification...")
            analysis = await self._analyze_with_ai(
                verification_message,
                context=f"Context: {context}"
            )

            if not analysis.get("is_verification", False):
                log.info("AI determined this is not a verification message")
                return VerificationResult(
                    success=True,
                    action_taken=None,
                    details={"ai_reasoning": analysis.get("reasoning")}
                )

            # Execute the action
            action = analysis.get("action", {})
            action_type = action.get("type", "none")

            log.info(f"AI suggests action: {action_type} (confidence: {analysis.get('confidence', 0):.0%})")

            success = await self._execute_action(action, verification_message)

            # Cache the action
            self.cache.set(
                bot_username or "unknown",
                verification_message.text or "",
                button_texts,
                CachedAction(
                    action_type=action_type,
                    action_data={k: v for k, v in action.items() if k != "type"},
                    success_count=1 if success else 0,
                    fail_count=0 if success else 1,
                ),
                self._our_username,
                self._our_first_name,
            )

            return VerificationResult(
                success=success,
                action_taken=action_type,
                cached=False,
                details={
                    "bot": bot_username,
                    "ai_reasoning": analysis.get("reasoning"),
                    "confidence": analysis.get("confidence"),
                }
            )

        except Exception as e:
            log.error(f"Verification check failed: {e}")
            return VerificationResult(
                success=False,
                error=str(e)
            )

    async def check_dm_verification(self, wait_seconds: float = 5.0) -> VerificationResult:
        """
        Check for verification DMs from bots after joining a channel.

        Some bots send private messages for verification.
        """
        await self._ensure_user_info()

        log.info("Checking for verification DMs...")

        await asyncio.sleep(wait_seconds)

        try:
            # Get recent dialogs
            async for dialog in self.client.iter_dialogs(limit=10):
                entity = dialog.entity

                # Check if it's a bot
                if not isinstance(entity, User) or not entity.bot:
                    continue

                # Check for recent messages from this bot
                async for message in self.client.iter_messages(entity, limit=3):
                    # Skip messages older than 30 seconds
                    if message.date and (datetime.utcnow() - message.date.replace(tzinfo=None)).seconds > 30:
                        continue

                    if message.sender_id != entity.id:
                        continue

                    # Check if it has buttons or looks like verification
                    if message.reply_markup or self._looks_like_verification(message.text):
                        log.info(f"Found verification DM from @{entity.username}")

                        # Handle it
                        return await self._handle_dm_verification(message, entity)

            log.debug("No verification DMs found")
            return VerificationResult(success=True, action_taken=None)

        except Exception as e:
            log.error(f"DM verification check failed: {e}")
            return VerificationResult(success=False, error=str(e))

    def _looks_like_verification(self, text: str | None) -> bool:
        """Check if message text looks like a verification challenge."""
        if not text:
            return False

        text_lower = text.lower()

        verification_keywords = [
            "verify", "verification", "captcha",
            "human", "robot", "bot",
            "prove", "confirm", "validate",
            "click", "press", "tap",
            "solve", "answer",
        ]

        return any(kw in text_lower for kw in verification_keywords)

    async def _handle_dm_verification(self, message: Message, bot: User) -> VerificationResult:
        """Handle a verification DM from a bot."""
        buttons = self._extract_buttons(message)
        button_texts = [b["text"] for b in buttons]

        # Check cache
        cached_action = self.cache.get(
            bot.username or "unknown",
            message.text or "",
            button_texts,
            self._our_username,
            self._our_first_name,
        )

        if cached_action:
            log.info(f"Using cached DM action: {cached_action.action_type}")
            success = await self._execute_action(
                {"type": cached_action.action_type, **cached_action.action_data},
                message
            )
            return VerificationResult(
                success=success,
                action_taken=cached_action.action_type,
                cached=True,
            )

        # Use AI
        analysis = await self._analyze_with_ai(message, context="DM verification")

        if not analysis.get("is_verification", False):
            return VerificationResult(success=True, action_taken=None)

        action = analysis.get("action", {})
        action_type = action.get("type", "none")

        success = await self._execute_action(action, message)

        # Cache
        self.cache.set(
            bot.username or "unknown",
            message.text or "",
            button_texts,
            CachedAction(
                action_type=action_type,
                action_data={k: v for k, v in action.items() if k != "type"},
                success_count=1 if success else 0,
                fail_count=0 if success else 1,
            ),
            self._our_username,
            self._our_first_name,
        )

        return VerificationResult(
            success=success,
            action_taken=action_type,
            cached=False,
        )
