"""The startup probe can run its sessions on a subscription token file, and never shows the token.

Given `--session-oauth-token-file`, every probe session holds that file's token as its
only credential, with no API key in its environment; the token reaches no output,
reading, baseline entry or error message; a missing, unreadable or empty file is
refused before any session starts; and the reading's profile names the subscription
route, while a reading taken without the file keeps today's profile.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers.startup_probe import (
    OPERATOR_API_KEY,
    PLANTED_TOKEN,
    TODAYS_EMPTY_DIR_PROFILE,
    ProbeRun,
    credentials_held,
    install_stand_in,
    make_unreadable,
    probe,
    running_as_root,
    token_file,
)


def test_every_probe_session_holds_the_files_token_as_its_only_credential(tmp_path: Path) -> None:
    stand_in = install_stand_in(tmp_path)

    run = probe(tmp_path, stand_in, session_token_file=token_file(tmp_path))

    assert run.exit_code == 0, run.everything_printed()[-2000:]
    assert run.sessions, "the probe started no session"
    assert [list(credentials_held(s).values()) for s in run.sessions] == [
        [PLANTED_TOKEN] for _ in run.sessions
    ], "a probe session held a credential other than the token, or no token"


def test_no_probe_session_sees_the_operators_api_key_when_a_token_file_is_given(
    tmp_path: Path,
) -> None:
    stand_in = install_stand_in(tmp_path)

    run = probe(tmp_path, stand_in, session_token_file=token_file(tmp_path))

    assert run.sessions, "the probe started no session"
    assert not any(OPERATOR_API_KEY in s["env"].values() for s in run.sessions), (
        "the operator's API key reached a session billed to the subscription"
    )


def test_a_token_a_session_echoes_reaches_no_output_or_reading_of_the_probe(
    tmp_path: Path,
) -> None:
    stand_in = install_stand_in(tmp_path, echo=True)

    run = probe(tmp_path, stand_in, session_token_file=token_file(tmp_path))

    assert run.sessions, "the probe started no session"
    assert PLANTED_TOKEN not in run.everything_printed(), "the probe printed the token"


def test_a_token_a_failing_session_echoes_reaches_no_error_message_of_the_probe(
    tmp_path: Path,
) -> None:
    stand_in = install_stand_in(tmp_path, echo=True, fail=True)

    run = probe(tmp_path, stand_in, session_token_file=token_file(tmp_path))

    assert run.sessions, "the probe started no session"
    assert PLANTED_TOKEN not in run.everything_printed(), "an error message carried the token"


def test_a_recorded_baseline_entry_never_carries_the_token(tmp_path: Path) -> None:
    stand_in = install_stand_in(tmp_path, echo=True)
    baseline = tmp_path / "startup_baseline.json"

    run = probe(tmp_path, stand_in, session_token_file=token_file(tmp_path), baseline=baseline)

    assert run.exit_code == 0, run.everything_printed()[-2000:]
    assert baseline.is_file(), "the probe recorded no baseline entry"
    assert PLANTED_TOKEN not in baseline.read_text(encoding="utf-8")


def assert_refused_naming(run: ProbeRun, path: Path) -> None:
    """A refusal of the token file itself: the option understood, the file named, nothing run."""
    printed = run.everything_printed()
    assert run.exit_code != 0, "the probe accepted an unusable token file"
    assert "unrecognized arguments" not in printed, f"the option itself was refused: {printed}"
    assert path.name in printed, f"the refusal does not name the token file: {printed}"
    assert run.sessions == [], "a session started before the token file was refused"


UNUSABLE_TOKEN_FILES = {"missing": None, "empty": "", "blank": "\n  \n"}


@pytest.mark.parametrize("content", UNUSABLE_TOKEN_FILES.values(), ids=UNUSABLE_TOKEN_FILES.keys())
def test_an_unusable_token_file_is_refused_before_any_session_starts(
    tmp_path: Path, content: str | None
) -> None:
    stand_in = install_stand_in(tmp_path)

    path = token_file(tmp_path, content)

    run = probe(tmp_path, stand_in, session_token_file=path)

    assert_refused_naming(run, path)


@pytest.mark.skipif(running_as_root(), reason="root reads a file whatever its mode")
def test_an_unreadable_token_file_is_refused_before_any_session_starts(tmp_path: Path) -> None:
    stand_in = install_stand_in(tmp_path)
    path = token_file(tmp_path)
    make_unreadable(path)

    run = probe(tmp_path, stand_in, session_token_file=path)

    assert_refused_naming(run, path)


def test_a_reading_on_the_subscription_names_its_route_in_its_profile(tmp_path: Path) -> None:
    stand_in = install_stand_in(tmp_path)

    profile = probe(tmp_path, stand_in, session_token_file=token_file(tmp_path)).reading["profile"]

    assert profile["key"] != TODAYS_EMPTY_DIR_PROFILE["key"], (
        "a subscription reading shares a profile with readings billed to the API key"
    )
    assert any(word in str(profile).lower() for word in ("subscription", "oauth")), (
        f"the profile does not name the credential route: {profile}"
    )
    assert PLANTED_TOKEN not in str(profile)


def test_a_reading_taken_without_a_token_file_keeps_todays_profile(tmp_path: Path) -> None:
    stand_in = install_stand_in(tmp_path)

    run = probe(tmp_path, stand_in)

    assert run.exit_code == 0, run.everything_printed()[-2000:]
    assert run.reading["profile"] == TODAYS_EMPTY_DIR_PROFILE
