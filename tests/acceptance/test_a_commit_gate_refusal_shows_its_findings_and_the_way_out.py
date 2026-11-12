"""Every commit-gate refusal the session reads carries the findings and the way out.

When the session commit gate refuses a call whose command carries `git commit`,
because the id-citation check found a violation or another check run through the gate
refused, the refusal the session reads carries the check's findings and says that no
command of that call ran, that the check judged the files as they stood before the
call began, and to fix and stage in one call and commit in a separate call. Run by
hand the id-citation check still shows its findings and keeps its exit codes; a call
the gate does not refuse is unchanged.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.acceptance.drivers.refusal_messages import (
    AC_VIOLATION,
    CITED_ID,
    CLEAN_CODE,
    ID_CITATION_CHECK,
    JUDGED_BEFORE_THE_CALL,
    NO_COMMAND_RAN,
    OTHER_CHECK_FINDING,
    STAGE_THEN_COMMIT_SEPARATELY,
    refusal_the_session_reads,
    refusing_check,
    run_commit_gate,
    run_id_citation_by_hand,
    says,
    staged_repo,
)

HINT = [
    pytest.param(NO_COMMAND_RAN, id="no-command-of-the-call-ran"),
    pytest.param(JUDGED_BEFORE_THE_CALL, id="judged-the-files-before-the-call"),
    pytest.param(STAGE_THEN_COMMIT_SEPARATELY, id="stage-then-commit-in-a-separate-call"),
]


def _id_citation_refusal(tmp_path: Path):
    repo = staged_repo(tmp_path, "src/widget.py", AC_VIOLATION)
    return run_commit_gate(repo, ID_CITATION_CHECK)


def _other_check_refusal(tmp_path: Path):
    repo = staged_repo(tmp_path, "src/widget.py", CLEAN_CODE)
    return run_commit_gate(repo, refusing_check(tmp_path))


REFUSALS = [
    pytest.param(_id_citation_refusal, id="id-citation-violation"),
    pytest.param(_other_check_refusal, id="another-check-refused"),
]


def test_an_id_citation_refusal_carries_its_finding_to_the_session(tmp_path: Path) -> None:
    run = _id_citation_refusal(tmp_path)

    refusal = refusal_the_session_reads(run)

    assert refusal is not None, f"the call was not refused: exit {run.exit_code}"
    assert "src/widget.py" in refusal, f"the session reads no finding:\n{refusal!r}"
    assert CITED_ID in refusal, (
        f"the session reads no finding:\n{refusal!r}"
    )  # id-citation-discipline:ignore


@pytest.mark.parametrize("refused", REFUSALS)
@pytest.mark.parametrize("statement", HINT)
def test_the_refusal_says_what_happened_to_the_call_and_how_to_retry(
    tmp_path: Path, refused, statement: str
) -> None:
    run = refused(tmp_path)

    refusal = refusal_the_session_reads(run)

    assert refusal is not None, f"the call was not refused: exit {run.exit_code}"
    assert says(refusal, statement), f"the refusal does not say /{statement}/:\n{refusal}"


def test_another_checks_refusal_still_carries_that_checks_own_finding(tmp_path: Path) -> None:
    run = _other_check_refusal(tmp_path)

    refusal = refusal_the_session_reads(run)

    assert refusal is not None
    assert OTHER_CHECK_FINDING in refusal, refusal


def test_the_id_citation_check_run_by_hand_still_shows_its_findings_and_exits_one(
    tmp_path: Path,
) -> None:
    repo = staged_repo(tmp_path, "src/widget.py", AC_VIOLATION)

    run = run_id_citation_by_hand(repo, "src/widget.py")

    assert run.exit_code == 1
    assert "src/widget.py" in run.stdout + run.stderr


def test_the_id_citation_check_run_by_hand_over_clean_code_exits_zero(tmp_path: Path) -> None:
    repo = staged_repo(tmp_path, "src/widget.py", CLEAN_CODE)

    run = run_id_citation_by_hand(repo, "src/widget.py")

    assert run.exit_code == 0, run.stdout + run.stderr


def test_a_commit_the_gate_does_not_refuse_passes_without_a_hint(tmp_path: Path) -> None:
    repo = staged_repo(tmp_path, "src/widget.py", CLEAN_CODE)

    run = run_commit_gate(repo, ID_CITATION_CHECK)

    assert run.exit_code == 0, run.stdout + run.stderr
    assert refusal_the_session_reads(run) is None
    assert not says(run.stdout + run.stderr, STAGE_THEN_COMMIT_SEPARATELY)
