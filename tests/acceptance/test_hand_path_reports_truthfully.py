"""A failing step on the hand path costs no other step, keeps working instructions, and is told.

When the instructions change cannot be written, `~/.claude/CLAUDE.md` still resolves to the
render it had or to the complete new one, never to a missing or half-written file; the rules and
the scripts are still offered and linked; the closing report names the failed step, the kind of
failure and how to finish; the run ends with a failure status and never prints the done line.
A failing scripts step likewise leaves the instructions finished. Under the stock macOS
`python3` (3.9) the command handles the instructions as it does under any newer interpreter.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess

import pytest

from tests.acceptance.drivers import hand_path_command as hc
from tests.acceptance.drivers import plugin_update as pu

pytestmark = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores the permissions these break"
)
FAILED = re.compile(r"could not|couldn't|failed|\bfail", re.IGNORECASE)
KIND = re.compile(r"writ|permission|denied|read", re.IGNORECASE)
HOW_TO_FINISH = re.compile(r"--complete-install|/praxion-complete-install")


@pytest.fixture(scope="module")
def sources(tmp_path_factory):
    root = tmp_path_factory.mktemp("sources")
    n = pu.shipped_tree(root / "n")
    n1 = pu.edited_template(pu.shipped_tree(root / "n1"), pu.with_release_notes)
    fresh = pu.fresh_install(root / "fresh", n1, pu.AFTER, pu.LATER)
    return n, n1, fresh


# -- The instructions step fails ------------------------------------------------------------------


@pytest.fixture(scope="module")
def instructions_failed(sources, tmp_path_factory):
    n, n1, fresh = sources
    update = pu.prepare_update(tmp_path_factory.mktemp("instructions-failed"), n, n1, fresh)
    restore = hc.blocked([((update.n1 / pu.RENDER).parent, 0o555),
                          (update.machine.home / ".claude", 0o555)])  # fmt: skip
    try:
        run = hc.run_command(update.n1, update.machine, hc.Person())
    finally:
        hc.restored(restore)
    return update, run


def test_a_failed_instructions_change_leaves_them_resolving_to_a_complete_render(
    instructions_failed,
):
    update, _ = instructions_failed
    complete = (update.n_render, pu.render(hc.n1_template(update), update.n_values))

    assert update.machine.instructions.exists(), "the instructions dangle after the failure"
    assert update.machine.instructions.read_text(encoding="utf-8") in complete


def test_a_failed_instructions_change_still_offers_and_links_the_rules_and_scripts(
    instructions_failed,
):
    update, run = instructions_failed

    assert run.asked("rules"), "the rules were not offered"
    assert run.asked("scripts"), "the scripts were not offered"
    assert hc.links_refreshed(update) == []


def test_a_failed_instructions_change_is_named_with_its_kind_and_how_to_finish(
    instructions_failed,
):
    _, run = instructions_failed
    said = run.instructions_report

    assert FAILED.search(said), f"the report never names the instructions as failed: {run.report}"
    assert KIND.search(said), f"the report never names the kind of failure: {run.report}"
    assert HOW_TO_FINISH.search("\n".join(run.report)), run.report


def test_a_failed_instructions_change_ends_with_a_failure_status_and_no_done_line(
    instructions_failed,
):
    _, run = instructions_failed

    assert run.exit_code not in (0, None), f"exit status {run.exit_code}"
    assert not run.says_done, run.report


# -- The scripts step fails -----------------------------------------------------------------------


@pytest.fixture(scope="module")
def scripts_failed(sources, tmp_path_factory):
    n, n1, fresh = sources
    update = pu.prepare_update(tmp_path_factory.mktemp("scripts-failed"), n, n1, fresh)
    restore = hc.blocked([(update.machine.bin, 0o555)])
    try:
        run = hc.run_command(update.n1, update.machine, hc.Person())
    finally:
        hc.restored(restore)
    return update, run


def test_a_failed_scripts_step_still_finishes_the_instructions(scripts_failed):
    update, _ = scripts_failed
    expected = pu.render(hc.n1_template(update), update.n_values)

    assert update.machine.instructions.read_text(encoding="utf-8") == expected


def test_a_failed_scripts_step_is_named_and_ends_with_a_failure_status(scripts_failed):
    _, run = scripts_failed
    named = [line for line in run.report if "script" in line.lower() and FAILED.search(line)]

    assert named, f"the report never names the scripts step as failed: {run.report}"
    assert run.exit_code not in (0, None), f"exit status {run.exit_code}"
    assert not run.says_done, run.report


# -- Stock macOS python3 --------------------------------------------------------------------------


def _python_3_9() -> str | None:
    for candidate in (shutil.which("python3.9"), "/usr/bin/python3"):
        if not candidate or not os.path.exists(candidate):
            continue
        probe = subprocess.run(
            [candidate, "-c", "import sys; print(sys.version_info[:2] == (3, 9))"],
            capture_output=True, text=True, timeout=60,
        )  # fmt: skip
        if probe.stdout.strip() == "True":
            return candidate
    return None


PYTHON_3_9 = _python_3_9()


@pytest.fixture(scope="module")
def under_python_3_9(sources, tmp_path_factory):
    n, n1, fresh = sources
    update = pu.prepare_update(tmp_path_factory.mktemp("python-3-9"), n, n1, fresh)
    target = update.n / pu.RENDER
    target.write_text(hc.unreadable(update, "hand-edited"), encoding="utf-8")
    run = hc.run_command(update.n1, update.machine, hc.Person(values=hc.TYPED), python=PYTHON_3_9)
    return update, run


@pytest.mark.skipif(PYTHON_3_9 is None, reason="no Python 3.9 on this machine to stand in for it")
def test_under_python_3_9_the_instructions_are_set_up_with_the_given_values(under_python_3_9):
    update, run = under_python_3_9
    expected = pu.render(hc.n1_template(update), hc.TYPED)

    assert "Traceback" not in run.transcript, run.transcript[-2000:]
    assert update.machine.instructions.read_text(encoding="utf-8") == expected
    assert not FAILED.search(run.instructions_report), run.report
