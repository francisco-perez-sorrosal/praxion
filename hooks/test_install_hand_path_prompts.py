"""Behavioral tests for the hand path's terminal conversation: the offer, the three values, the confirmation.

These run over `io.StringIO` streams and need no home, plugin cache or git: the step's own
tests, which do, are in `test_install_hand_path.py`.
"""

from __future__ import annotations

import io

import _install_hand_path as hand_path
import pytest

INSTRUCTIONS = "~/.claude/CLAUDE.md"


class TestOffer:
    @pytest.mark.parametrize(("answer", "accepted"), [("\n", True), ("1\n", True), ("2\n", False)])
    def test_the_choice_is_read_from_the_input(self, answer, accepted):
        stderr = io.StringIO()

        assert hand_path.ask_offer("why", io.StringIO(answer), stderr) is accepted

    def test_the_offer_names_the_change_the_skip_and_why_in_the_designed_shape(self):
        stderr = io.StringIO()

        hand_path.ask_offer("It is old.", io.StringIO("1\n"), stderr)

        assert stderr.getvalue().splitlines() == [
            "",
            "It is old.",
            f"  [1] Bring {INSTRUCTIONS} to this version",
            "  [2] Skip instructions",
            "Choice [1]: ",
        ]

    def test_an_invalid_choice_asks_again(self):
        stderr = io.StringIO()

        accepted = hand_path.ask_offer("why", io.StringIO("x\n3\n2\n"), stderr)

        assert accepted is False
        assert stderr.getvalue().count("Choice [1]: ") == 3
        assert stderr.getvalue().count("Please answer 1 or 2.") == 2

    def test_the_input_ending_is_no_answer(self):
        with pytest.raises(hand_path.InputEndedError):
            hand_path.ask_offer("why", io.StringIO(""), io.StringIO())

    def test_the_input_ending_finishes_the_prompts_line(self):
        stderr = io.StringIO()

        with pytest.raises(hand_path.InputEndedError):
            hand_path.ask_offer("why", io.StringIO(""), stderr)

        assert stderr.getvalue().endswith("Choice [1]: \n")


class TestValues:
    DEFAULTS = {"USERNAME": "@derived", "EMAIL": "derived@example.invalid", "GITHUB_URL": "u://d"}

    def test_enter_at_each_prompt_takes_the_derived_value(self):
        values = hand_path.ask_values(self.DEFAULTS, io.StringIO("\n\n\n"), io.StringIO())

        assert values == self.DEFAULTS

    @pytest.mark.parametrize(
        "prompt",
        ["Username [@derived]: ", "Email [derived@example.invalid]: ", "GitHub URL [u://d]: "],
    )
    def test_each_prompt_shows_its_derived_value_in_brackets(self, prompt):
        stderr = io.StringIO()

        hand_path.ask_values(self.DEFAULTS, io.StringIO("\n\n\n"), stderr)

        assert prompt in stderr.getvalue()

    def test_a_typed_value_wins_and_is_stripped(self):
        answers = "  @typed  \n\ntyped@example.invalid\n"

        values = hand_path.ask_values(self.DEFAULTS, io.StringIO(answers), io.StringIO())

        assert values == {
            "USERNAME": "@typed",
            "EMAIL": self.DEFAULTS["EMAIL"],
            "GITHUB_URL": "typed@example.invalid",
        }

    @pytest.mark.parametrize("answered", [0, 1, 2])
    def test_the_input_ending_at_any_value_is_no_answer(self, answered):
        answers = "\n" * answered

        with pytest.raises(hand_path.InputEndedError):
            hand_path.ask_values(self.DEFAULTS, io.StringIO(answers), io.StringIO())


class TestConfirmation:
    VALUES = {"USERNAME": "@shown", "EMAIL": "shown@example.invalid", "GITHUB_URL": "u://s"}

    @pytest.mark.parametrize(
        ("answer", "confirmed"),
        [("\n", True), ("y\n", True), ("Y\n", True), ("n\n", False), ("N\n", False)],
    )
    def test_enter_or_y_confirms_and_n_declines(self, answer, confirmed):
        assert (
            hand_path.confirm_values(self.VALUES, io.StringIO(answer), io.StringIO()) is confirmed
        )

    def test_anything_else_asks_again(self):
        stderr = io.StringIO()

        confirmed = hand_path.confirm_values(self.VALUES, io.StringIO("maybe\nyes\nn\n"), stderr)

        assert confirmed is False
        assert stderr.getvalue().count("[Y/n]: ") == 3
        assert stderr.getvalue().count("Please answer y or n.") == 2

    def _last_lines(self) -> list[str]:
        stderr = io.StringIO()
        hand_path.confirm_values(self.VALUES, io.StringIO("\n"), stderr)
        return [line for line in stderr.getvalue().splitlines() if line.strip()][-6:]

    def test_the_last_line_asks_whether_to_write_them(self):
        assert self._last_lines()[-1] == f"Write these to {INSTRUCTIONS}? [Y/n]: "

    @pytest.mark.parametrize("key", ["USERNAME", "EMAIL", "GITHUB_URL"])
    def test_the_last_lines_show_each_value(self, key):
        shown = "\n".join(self._last_lines())

        assert self.VALUES[key] in shown, shown

    def test_the_last_lines_never_say_default(self):
        shown = "\n".join(self._last_lines())

        assert "default" not in shown.lower(), shown

    def test_the_input_ending_is_no_answer(self):
        with pytest.raises(hand_path.InputEndedError):
            hand_path.confirm_values(self.VALUES, io.StringIO(""), io.StringIO())
