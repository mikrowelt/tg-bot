import json
import base64
import asyncio
import urllib.request
import urllib.parse

from ..utils.logger import setup_logger

log = setup_logger("tg-bot.verification.captcha")


class CaptchaError(Exception):
    """Raised when captcha solving fails."""
    pass


class CaptchaSolver:
    """Solves image captchas using 2captcha API."""

    BASE_URL = "http://2captcha.com"

    def __init__(self, api_key: str | None):
        self.api_key = api_key

    async def solve(self, image_bytes: bytes) -> str:
        """Solve an image captcha and return the answer."""
        if not self.api_key:
            log.warning("2captcha API key not configured")
            raise CaptchaError("2captcha API key not configured")

        try:
            # Submit captcha
            log.debug("Submitting captcha to 2captcha...")
            b64_image = base64.b64encode(image_bytes).decode()
            submit_data = urllib.parse.urlencode({
                "key": self.api_key,
                "method": "base64",
                "body": b64_image,
                "json": 1
            }).encode()

            req = urllib.request.Request(f"{self.BASE_URL}/in.php", data=submit_data)
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())

            if result.get("status") != 1:
                log.error(f"Captcha submit failed: {result.get('request')}")
                raise CaptchaError(f"Submit failed: {result.get('request', 'Unknown error')}")

            captcha_id = result["request"]
            log.info(f"Captcha submitted (ID: {captcha_id})")

            # Poll for result
            await asyncio.sleep(10)
            for attempt in range(12):  # Max 60 seconds
                log.debug(f"Polling for result (attempt {attempt + 1}/12)...")
                result_params = urllib.parse.urlencode({
                    "key": self.api_key,
                    "action": "get",
                    "id": captcha_id,
                    "json": 1
                })
                result_url = f"{self.BASE_URL}/res.php?{result_params}"
                with urllib.request.urlopen(result_url, timeout=30) as resp:
                    result = json.loads(resp.read().decode())

                if result.get("status") == 1:
                    log.info(f"Captcha solved: {result['request']}")
                    return result["request"]
                elif result.get("request") != "CAPCHA_NOT_READY":
                    log.error(f"Captcha solve failed: {result.get('request')}")
                    raise CaptchaError(f"Solve failed: {result.get('request', 'Unknown error')}")

                await asyncio.sleep(5)

            log.error("Captcha solving timeout")
            raise CaptchaError("Captcha solving timeout")

        except urllib.error.URLError as e:
            log.error(f"Network error: {e}")
            raise CaptchaError(f"Network error: {e}")
        except json.JSONDecodeError as e:
            log.error(f"Invalid response from 2captcha: {e}")
            raise CaptchaError(f"Invalid response: {e}")
