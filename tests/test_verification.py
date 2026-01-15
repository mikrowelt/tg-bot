"""Tests for tgbot.verification module."""

import pytest

from tgbot.verification.math_solver import MathSolver


class TestMathSolver:
    """Tests for MathSolver class."""

    class TestAddition:
        """Tests for addition operations."""

        def test_simple_addition(self):
            """Test simple addition."""
            result = MathSolver.solve("What is 2 + 3?")
            assert result == "5"

        def test_addition_with_spaces(self):
            """Test addition with various spacing."""
            assert MathSolver.solve("5+3") == "8"
            assert MathSolver.solve("5 + 3") == "8"
            assert MathSolver.solve("5  +  3") == "8"

        def test_addition_large_numbers(self):
            """Test addition with larger numbers."""
            result = MathSolver.solve("Calculate: 123 + 456")
            assert result == "579"

        def test_addition_in_sentence(self):
            """Test addition embedded in text."""
            result = MathSolver.solve("Please solve 10 + 20 to verify")
            assert result == "30"

    class TestSubtraction:
        """Tests for subtraction operations."""

        def test_simple_subtraction(self):
            """Test simple subtraction."""
            result = MathSolver.solve("What is 10 - 3?")
            assert result == "7"

        def test_subtraction_with_spaces(self):
            """Test subtraction with various spacing."""
            assert MathSolver.solve("15-7") == "8"
            assert MathSolver.solve("15 - 7") == "8"
            assert MathSolver.solve("15  -  7") == "8"

        def test_subtraction_result_zero(self):
            """Test subtraction resulting in zero."""
            result = MathSolver.solve("5 - 5 equals")
            assert result == "0"

        def test_subtraction_negative_result(self):
            """Test subtraction with negative result."""
            result = MathSolver.solve("3 - 10")
            assert result == "-7"

    class TestMultiplication:
        """Tests for multiplication operations."""

        def test_multiplication_asterisk(self):
            """Test multiplication with asterisk."""
            result = MathSolver.solve("6 * 7")
            assert result == "42"

        def test_multiplication_x(self):
            """Test multiplication with x."""
            result = MathSolver.solve("6 x 7")
            assert result == "42"

        def test_multiplication_times_symbol(self):
            """Test multiplication with × symbol."""
            result = MathSolver.solve("6 × 7")
            assert result == "42"

        def test_multiplication_large_numbers(self):
            """Test multiplication with larger numbers."""
            result = MathSolver.solve("Calculate 12 * 12")
            assert result == "144"

        def test_multiplication_by_zero(self):
            """Test multiplication by zero."""
            result = MathSolver.solve("999 * 0")
            assert result == "0"

        def test_multiplication_by_one(self):
            """Test multiplication by one."""
            result = MathSolver.solve("42 * 1")
            assert result == "42"

    class TestDivision:
        """Tests for division operations."""

        def test_division_slash(self):
            """Test division with slash."""
            result = MathSolver.solve("20 / 4")
            assert result == "5"

        def test_division_symbol(self):
            """Test division with ÷ symbol."""
            result = MathSolver.solve("20 ÷ 4")
            assert result == "5"

        def test_division_integer_result(self):
            """Test division returns integer division."""
            result = MathSolver.solve("10 / 3")
            assert result == "3"  # Integer division

        def test_division_by_zero(self):
            """Test division by zero returns None."""
            result = MathSolver.solve("10 / 0")
            assert result is None  # Division by zero returns None

        def test_division_large_numbers(self):
            """Test division with larger numbers."""
            result = MathSolver.solve("1000 / 25")
            assert result == "40"

    class TestNoMathProblem:
        """Tests for text without math problems."""

        def test_no_math_returns_none(self):
            """Test that text without math returns None."""
            result = MathSolver.solve("Hello, welcome to our channel!")
            assert result is None

        def test_empty_string(self):
            """Test empty string returns None."""
            result = MathSolver.solve("")
            assert result is None

        def test_only_numbers_no_operator(self):
            """Test numbers without operator returns None."""
            result = MathSolver.solve("Enter code 12345")
            assert result is None

        def test_text_with_numbers_but_no_math(self):
            """Test text with numbers but no math expression."""
            result = MathSolver.solve("You are user #42 in the queue")
            assert result is None

    class TestEdgeCases:
        """Tests for edge cases."""

        def test_multiple_operations_returns_first(self):
            """Test that first operation is solved when multiple exist."""
            result = MathSolver.solve("2 + 3 and also 4 * 5")
            assert result == "5"  # First match: 2 + 3

        def test_zero_operands(self):
            """Test operations with zero."""
            assert MathSolver.solve("0 + 5") == "5"
            assert MathSolver.solve("5 + 0") == "5"
            assert MathSolver.solve("0 - 0") == "0"

        def test_single_digit_numbers(self):
            """Test single digit operations."""
            assert MathSolver.solve("1 + 1") == "2"
            assert MathSolver.solve("9 - 1") == "8"

        def test_multiline_text(self):
            """Test math in multiline text."""
            text = """
            Welcome to verification!
            Please solve: 7 + 8
            Thank you.
            """
            result = MathSolver.solve(text)
            assert result == "15"

        def test_unicode_text_with_math(self):
            """Test math extraction from unicode text."""
            result = MathSolver.solve("Решите: 15 + 25 чтобы продолжить")
            assert result == "40"

        def test_math_with_punctuation(self):
            """Test math followed by punctuation."""
            assert MathSolver.solve("What is 5+5?") == "10"
            assert MathSolver.solve("Answer: 3*4.") == "12"
            assert MathSolver.solve("(8-2)") == "6"
