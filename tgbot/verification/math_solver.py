import re

from ..utils.logger import setup_logger

log = setup_logger("tg-bot.verification.math")


class MathSolver:
    """Extracts and solves math problems from text."""

    PATTERNS = [
        (r"(\d+)\s*[\+]\s*(\d+)", "+", lambda a, b: a + b),
        (r"(\d+)\s*[\-]\s*(\d+)", "-", lambda a, b: a - b),
        (r"(\d+)\s*[\*x×]\s*(\d+)", "*", lambda a, b: a * b),
        (r"(\d+)\s*[\/÷]\s*(\d+)", "/", lambda a, b: a // b if b != 0 else 0),
    ]

    @classmethod
    def solve(cls, text: str) -> str | None:
        """
        Extract and solve a math problem from text.
        Returns the answer as a string, or None if no problem found.
        """
        for pattern, op, operation in cls.PATTERNS:
            match = re.search(pattern, text)
            if match:
                a, b = int(match.group(1)), int(match.group(2))
                result = operation(a, b)
                log.info(f"Math solved: {a} {op} {b} = {result}")
                return str(result)

        log.debug("No math problem found in text")
        return None
