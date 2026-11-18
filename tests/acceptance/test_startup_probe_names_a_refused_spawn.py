"""The startup instrument names a refused spawn instead of reporting a timeout.

When the stream of an agent target's session shows the harness refused the `Agent` call, the
target is withheld with a reason that names the refusal and carries its text, cut to a bounded
length. A session that ended before the timeout is never described as having run for the whole
timeout; a session that ran on without spawning is withheld for the timeout as before. The
sessions are started exactly as before, with no pre-approval of the `Agent` tool.
"""

from __future__ import annotations

import re

from tests.acceptance.drivers.refused_spawn import (
    LONG_REFUSAL,
    REFUSAL,
    TIMEOUT_SECONDS,
    base_agent_argv,
    read_agent_target,
)

REFUSAL_WORD = re.compile(r"\brefus", re.IGNORECASE)
WHOLE_TIMEOUT = re.compile(rf"\b{TIMEOUT_SECONDS}\s?(?:s|sec|seconds)\b")


def test_a_refused_spawn_is_withheld_with_a_reason_naming_the_refusal_and_its_text(tmp_path):
    reading = read_agent_target(tmp_path, "refused")

    reason = reading.withheld() or ""

    assert REFUSAL_WORD.search(reason), f"the reason does not name a refusal: {reason!r}"
    assert REFUSAL in reason, f"the reason does not carry the refusal's text: {reason!r}"


def test_a_refused_spawn_is_not_described_as_running_for_the_whole_timeout(tmp_path):
    reading = read_agent_target(tmp_path, "refused")

    reason = reading.withheld() or ""

    assert reason, "the refused target was not withheld"
    assert not WHOLE_TIMEOUT.search(reason), f"the reason claims the whole timeout: {reason!r}"


def test_a_long_refusal_is_carried_cut_to_a_bounded_length(tmp_path):
    reading = read_agent_target(tmp_path, "refused_at_length")

    reason = reading.withheld() or ""

    assert REFUSAL in reason, f"the reason lost the refusal's opening text: {reason[:300]!r}"
    assert len(reason) < len(LONG_REFUSAL), f"the reason carries all {len(reason)} characters"


def test_a_session_that_ended_early_without_spawning_is_not_described_as_timing_out(tmp_path):
    reading = read_agent_target(tmp_path, "ended")

    reason = reading.withheld() or ""

    assert reason, "a session that spawned nothing was not withheld"
    assert not WHOLE_TIMEOUT.search(reason), f"the reason claims the whole timeout: {reason!r}"


def test_a_session_that_runs_on_without_spawning_is_withheld_for_the_timeout_as_before(tmp_path):
    reading = read_agent_target(tmp_path, "runs_on")

    reason = reading.withheld() or ""

    assert WHOLE_TIMEOUT.search(reason), f"the reason does not name the timeout: {reason!r}"
    assert not REFUSAL_WORD.search(reason), f"a session that ran on is called refused: {reason!r}"


def test_the_agent_session_is_started_exactly_as_before(tmp_path):
    reading = read_agent_target(tmp_path, "refused")

    assert reading.session_argvs, "the instrument started no session"
    assert reading.session_argvs[-1] == base_agent_argv()
