"""Recording-mode resolution: one precedence chain over the environment.

The legacy kill switch wins; then the mode setting, case-insensitively; a
setting naming no mode falls back to ``full`` (a typo keeps evidence rather
than losing it); with neither set -- including an explicit ``"0"`` on the
legacy switch -- the default is ``standard``.
"""

from __future__ import annotations

import pytest

from hooks._observation_log.modes import Mode, ModeSource, resolve_mode


def test_an_empty_environment_resolves_to_the_standard_default() -> None:
    assert resolve_mode({}) == (Mode.STANDARD, ModeSource.DEFAULT)


def test_an_explicitly_falsy_legacy_switch_is_neutral_and_resolves_to_standard() -> None:
    assert resolve_mode({"PRAXION_DISABLE_OBSERVABILITY": "0"}) == (
        Mode.STANDARD,
        ModeSource.DEFAULT,
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("full", Mode.FULL),
        ("standard", Mode.STANDARD),
        ("off", Mode.OFF),
        ("OFF", Mode.OFF),
        ("Standard", Mode.STANDARD),
        (" FULL ", Mode.FULL),
    ],
)
def test_the_mode_setting_is_read_case_insensitively(value: str, expected: Mode) -> None:
    assert resolve_mode({"PRAXION_OBSERVATION_LOG": value}) == (expected, ModeSource.SETTING)


def test_a_setting_naming_no_mode_falls_back_to_full() -> None:
    assert resolve_mode({"PRAXION_OBSERVATION_LOG": "verbose"}) == (
        Mode.FULL,
        ModeSource.INVALID_SETTING,
    )


def test_a_truthy_legacy_switch_wins_over_an_explicit_mode_setting() -> None:
    env = {"PRAXION_DISABLE_OBSERVABILITY": "1", "PRAXION_OBSERVATION_LOG": "full"}
    assert resolve_mode(env) == (Mode.OFF, ModeSource.LEGACY_DISABLE)
