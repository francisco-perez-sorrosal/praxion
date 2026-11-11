"""What the first-session hook means the user to read reaches them as the one message they see.

Claude Code shows the user the `systemMessage` of the JSON object a session-start hook writes as
its whole standard output, and shows no one the standard error of a hook that exits 0. So a first
install's completion line, and the line naming `/praxion-complete-install` when a first install
fails, arrive in that message and nowhere else. When the notice that `python3` is below the hooks'
floor fires in the same session start as an install or refresh report, both arrive in the one
object, each on its own line. A session start with nothing to report writes nothing at all.
"""

from __future__ import annotations

import os

import pytest

from tests.acceptance.drivers import hook_reports as hr
from tests.acceptance.drivers import plugin_update as pu

pytestmark = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores the permissions these break"
)


@pytest.fixture(scope="module")
def tree(tmp_path_factory):
    return pu.shipped_tree(tmp_path_factory.mktemp("tree"))


@pytest.fixture(scope="module")
def below_floor(tmp_path_factory):
    python = hr.below_floor_python(tmp_path_factory.mktemp("below-floor") / "env")
    if python is None:
        pytest.skip(
            "PyYAML is importable from this interpreter's base, so no python3 below the floor"
        )
    return python


# -- A first install that fails -------------------------------------------------------------------


@pytest.fixture(
    scope="module", params=["scripts-directory-not-writable", "claude-directory-not-writable"]
)
def failed_install(request, tree, tmp_path_factory):
    return hr.first_install(tmp_path_factory.mktemp(request.param), tree, failing=request.param)


def test_a_failed_first_install_ends_with_a_success_status(failed_install):
    assert not failed_install.session.timed_out
    assert failed_install.session.exit_code == 0


def test_a_failed_first_install_reports_one_line_naming_the_command_to_finish_by_hand(
    failed_install,
):
    lines = hr.message_lines(failed_install.session)
    assert len(lines) == 1, f"expected one report line in the message, got {lines}"
    assert lines[0].startswith(hr.PREFIX), lines[0]
    assert hr.FINISH_BY_HAND in lines[0], lines[0]


def test_a_failed_first_install_writes_its_report_nowhere_but_the_message(failed_install):
    assert hr.FINISH_BY_HAND not in failed_install.session.stderr, failed_install.session.stderr


def test_a_failed_first_install_report_carries_no_personal_value_or_exception_text(failed_install):
    text = hr.message(failed_install.session)
    leaked = sorted(v for v in failed_install.identity_values if v in text)
    assert not leaked, f"the report carries personal values: {leaked}"
    assert "Errno" not in text, f"the report carries an exception's message: {text}"
    assert str(failed_install.machine.root) not in text, f"the report carries a path: {text}"


# -- A first install that completes ---------------------------------------------------------------


@pytest.fixture(scope="module")
def completed_install(tree, tmp_path_factory):
    return hr.first_install(tmp_path_factory.mktemp("completed"), tree)


def test_a_completed_first_install_says_so_in_its_message(completed_install):
    assert hr.message_lines(completed_install.session) == [hr.COMPLETED]


def test_a_completed_first_install_writes_its_completion_line_nowhere_but_the_message(
    completed_install,
):
    assert hr.COMPLETED not in completed_install.session.stderr, completed_install.session.stderr


def test_a_completed_first_install_message_carries_no_personal_value(completed_install):
    text = hr.message(completed_install.session)
    leaked = sorted(v for v in completed_install.identity_values if v in text)
    assert not leaked, f"the message carries personal values: {leaked}"


# -- The floor notice beside another report -------------------------------------------------------


@pytest.fixture(scope="module")
def lone_notice(tree, below_floor, tmp_path_factory):
    """An update that succeeds under a python3 below the floor: the notice is its only report."""
    return hr.update(tmp_path_factory.mktemp("lone-notice"), tree, python=below_floor)


@pytest.fixture(scope="module")
def notice(lone_notice):
    return hr.message_lines(lone_notice.session)[0]


def test_a_lone_floor_notice_arrives_as_the_one_message(lone_notice):
    lines = hr.message_lines(lone_notice.session)
    assert len(lines) == 1, f"expected the notice alone, got {lines}"
    assert lines[0].startswith(hr.PREFIX), lines[0]
    assert lines[0] not in lone_notice.session.stderr, lone_notice.session.stderr


@pytest.fixture(scope="module")
def notice_and_failed_refresh(tree, below_floor, tmp_path_factory):
    return hr.update(
        tmp_path_factory.mktemp("notice-and-refresh"),
        tree,
        failing="scripts-directory-not-writable",
        python=below_floor,
    )


def test_a_floor_notice_and_a_failed_refresh_share_one_message_each_on_its_own_line(
    notice_and_failed_refresh, notice
):
    session = notice_and_failed_refresh.session
    lines = hr.message_lines(session)
    refresh_lines = [line for line in lines if line != notice]
    assert len(lines) == 2, f"expected the notice and the refresh report, got {lines}"
    assert notice in lines, f"the floor notice is missing from {lines}"
    assert refresh_lines[0].startswith(hr.PREFIX), refresh_lines[0]
    assert hr.FINISH_BY_HAND in refresh_lines[0], refresh_lines[0]
    assert session.exit_code == 0


def test_a_floor_notice_and_a_failed_refresh_write_neither_report_to_standard_error(
    notice_and_failed_refresh, notice
):
    stderr = notice_and_failed_refresh.session.stderr
    assert hr.FINISH_BY_HAND not in stderr, stderr
    assert notice not in stderr, stderr


@pytest.fixture(scope="module")
def notice_and_completed_install(tree, below_floor, tmp_path_factory):
    return hr.first_install(tmp_path_factory.mktemp("notice-and-install"), tree, python=below_floor)


def test_a_floor_notice_and_a_completed_install_share_one_message_each_on_its_own_line(
    notice_and_completed_install, notice
):
    lines = hr.message_lines(notice_and_completed_install.session)
    assert sorted(lines) == sorted([notice, hr.COMPLETED])


def test_a_floor_notice_and_a_completed_install_write_neither_report_to_standard_error(
    notice_and_completed_install, notice
):
    stderr = notice_and_completed_install.session.stderr
    assert hr.COMPLETED not in stderr, stderr
    assert notice not in stderr, stderr


# -- Nothing to report ----------------------------------------------------------------------------


QUIET_STARTS = {
    "successful-update": hr.update,
    "later-session-of-the-same-version": hr.later_session,
    "opted-out": hr.opted_out,
    "no-plugin-root-and-no-registry": hr.no_plugin_root_anywhere,
    "plugin-root-and-registry-naming-no-directory": hr.plugin_root_naming_nothing,
}


@pytest.fixture(scope="module", params=sorted(QUIET_STARTS))
def quiet(request, tree, tmp_path_factory):
    return QUIET_STARTS[request.param](tmp_path_factory.mktemp(request.param), tree)


def test_a_session_start_with_nothing_to_report_writes_nothing_to_either_stream(quiet):
    session = quiet.session
    assert session.exit_code == 0
    assert (session.stdout, session.stderr) == ("", "")
