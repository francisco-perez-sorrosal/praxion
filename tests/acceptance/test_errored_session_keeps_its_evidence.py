"""An errored session keeps a bounded tail of its error output and its result text, never a secret.

The tails are each at most the bound the run declares before its first launch; an empty
stream is recorded as empty; a credential a session wrote into either stream reaches
neither the results file nor the report; the report shows each errored session's tails.
"""

from __future__ import annotations

from pathlib import Path

from tests.acceptance.drivers import adherence_runs as runs
from tests.acceptance.drivers.adherence_runs import (
    PLANTED_SECRET,
    Plan,
    Script,
    crashed,
    error_result,
)

LONG_PREFIX = "".join(f"diagnostic line {i:04d} of a long failure\n" for i in range(400))
CLOSING = "the closing words of the failure: stream closed by peer"


def one_errored_lean_session(tmp_path: Path, ending: runs.Ending) -> runs.StandInRun:
    checkout = runs.new_checkout(tmp_path)
    plan = Plan(max_tasks=1)
    return runs.run_with_stand_in(tmp_path, checkout, plan, Script(by_arm={"lean": [ending]}))


def test_an_errored_sessions_record_keeps_the_end_of_its_error_output_within_the_bound(
    tmp_path: Path,
) -> None:
    result = one_errored_lean_session(tmp_path, crashed(LONG_PREFIX + CLOSING))

    tails = runs.error_tails(result.results_path)
    bound = runs.declared_tail_bound(result.results_path)

    assert tails, "no errored session recorded its tails"
    assert all(0 < len(t.error_output) <= bound for t in tails)
    assert all((LONG_PREFIX + CLOSING).endswith(t.error_output) for t in tails)
    assert all(t.error_output.endswith(CLOSING) for t in tails)


def test_an_errored_sessions_record_keeps_the_end_of_its_result_text_within_the_bound(
    tmp_path: Path,
) -> None:
    result = one_errored_lean_session(tmp_path, error_result(LONG_PREFIX + CLOSING))

    tails = runs.error_tails(result.results_path)
    bound = runs.declared_tail_bound(result.results_path)

    assert tails, "no errored session recorded its tails"
    assert all(0 < len(t.result_text) <= bound for t in tails)
    assert all(t.result_text.endswith(CLOSING) for t in tails)


def test_an_empty_stream_is_recorded_as_empty_never_omitted(tmp_path: Path) -> None:
    result = one_errored_lean_session(tmp_path, crashed(""))

    tails = runs.error_tails(result.results_path)

    assert tails, "no errored session recorded its tails"
    assert [t.error_output for t in tails] == ["" for _ in tails]


def test_a_credential_in_a_sessions_streams_reaches_neither_the_results_file_nor_the_report(
    tmp_path: Path,
) -> None:
    leak = f"auth failed for token {PLANTED_SECRET}; aborting"
    result = one_errored_lean_session(tmp_path, error_result(leak, error_output=leak))

    report = runs.run_report(tmp_path, result.results_path)

    assert runs.error_tails(result.results_path), "no errored session recorded its tails"
    assert PLANTED_SECRET not in result.results_path.read_text(encoding="utf-8")
    assert PLANTED_SECRET not in report


def test_the_report_shows_each_errored_sessions_tails(tmp_path: Path) -> None:
    result = one_errored_lean_session(tmp_path, error_result(CLOSING, error_output=CLOSING))

    report = runs.run_report(tmp_path, result.results_path)

    assert CLOSING in report, "the report does not show the errored session's tails"
