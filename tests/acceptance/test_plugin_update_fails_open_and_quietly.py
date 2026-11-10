"""The first-session refresh never blocks a session, keeps the instructions whole, and stays quiet.

A refresh that fails (a directory not writable, a file that cannot be read) still ends the
session-start step with a success status and reports itself in one line naming the command that
finishes the job by hand; `~/.claude/CLAUDE.md` always resolves to a complete render. A later
session of the same version changes nothing and prints nothing, and no personal value ever
reaches the session's output or a log.
"""

from __future__ import annotations

import os
import time

import pytest

from tests.acceptance.drivers import plugin_update as pu

pytestmark = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores the permissions these break"
)
MIN_VALUE_LENGTH = 5  # shorter strings occur by chance in any output
FINISH_BY_HAND = ("install.sh", "praxion-complete-install")


@pytest.fixture(scope="module")
def sources(tmp_path_factory):
    root = tmp_path_factory.mktemp("sources")
    n = pu.shipped_tree(root / "n")
    n1 = pu.edited_template(pu.shipped_tree(root / "n1"), pu.with_release_notes)
    fresh = pu.fresh_install(root / "fresh", n1, pu.AFTER, pu.LATER)
    return n, n1, fresh


def _break(update: pu.Update, how: str) -> list:
    """Make one step of the refresh fail; returns (path, mode) pairs to restore."""
    targets = {
        "scripts-directory-not-writable": [(update.machine.bin, 0o555)],
        "template-unreadable": [(update.n1 / pu.TEMPLATE, 0o000)],
        "render-not-writable": [
            ((update.n1 / pu.TEMPLATE).parent, 0o555),
            (update.machine.home / ".claude", 0o555),
        ],
    }[how]
    restore = []
    for path, mode in targets:
        restore.append((path, path.stat().st_mode & 0o7777))
        path.chmod(mode)
    return restore


@pytest.fixture(
    scope="module",
    params=["scripts-directory-not-writable", "template-unreadable", "render-not-writable"],
)
def failed(request, sources, tmp_path_factory):
    n, n1, fresh = sources
    update = pu.prepare_update(tmp_path_factory.mktemp(request.param), n, n1, fresh)
    restore = _break(update, request.param)
    update.run()
    yield update, (n1 / pu.TEMPLATE).read_text(encoding="utf-8")
    for path, mode in reversed(restore):
        path.chmod(mode)


def test_a_failed_refresh_ends_the_session_start_step_with_a_success_status(failed):
    failed, _ = failed
    assert not failed.session.timed_out
    assert failed.session.exit_code == 0


def test_a_failed_refresh_reports_itself_in_one_line_naming_the_command_to_finish_by_hand(failed):
    failed, _ = failed
    lines = failed.session.lines
    assert len(lines) == 1, f"expected one report line, got {len(lines)}: {lines}"
    assert any(command in lines[0] for command in FINISH_BY_HAND), lines[0]


def test_a_failed_refresh_leaves_the_instructions_resolving_to_a_complete_render(failed):
    update, n1_template = failed
    expected_n1 = pu.render(n1_template, update.n_values)
    text = update.machine.instructions.read_text(encoding="utf-8")
    assert text in (update.n_render, expected_n1), "the instructions are neither N's nor N+1's"


# -- Later sessions ---------------------------------------------------------------------------------


@pytest.fixture(scope="module", params=["succeeded", "failed"])
def second_session(request, sources, tmp_path_factory):
    n, n1, fresh = sources
    update = pu.prepare_update(tmp_path_factory.mktemp(f"second-{request.param}"), n, n1, fresh)
    restore = _break(update, "scripts-directory-not-writable") if request.param == "failed" else []
    update.run()
    before = pu.snapshot(update.machine.home)
    later = update.machine.session(pu.AFTER)
    yield before, pu.snapshot(update.machine.home), later
    for path, mode in reversed(restore):
        path.chmod(mode)


def test_a_later_session_of_the_same_version_changes_no_file_or_link(second_session):
    before, after, _ = second_session
    changed = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
    assert not changed, f"a later session changed: {changed[:20]}"


def test_a_later_session_of_the_same_version_prints_nothing(second_session):
    *_, later = second_session
    assert later.exit_code == 0
    assert later.lines == []


# -- Personal values --------------------------------------------------------------------------------


@pytest.fixture(scope="module", params=["succeeded", "scripts-directory-not-writable"])
def observed(request, sources, tmp_path_factory):
    n, n1, fresh = sources
    update = pu.prepare_update(tmp_path_factory.mktemp(f"values-{request.param}"), n, n1, fresh)
    restore = [] if request.param == "succeeded" else _break(update, request.param)
    started = time.time()
    update.run()
    template = (n1 / pu.TEMPLATE).read_text(encoding="utf-8")
    values = {*update.n_values.values(), *pu.values_in(fresh.instructions, template).values()}
    values |= {pu.FIRST.email, pu.LATER.email, pu.FIRST.name, pu.LATER.name}
    yield update, started, {v for v in values if len(v) >= MIN_VALUE_LENGTH}
    for path, mode in reversed(restore):
        path.chmod(mode)


def test_the_refresh_prints_no_personal_value(observed):
    update, _, values = observed
    output = update.session.stdout + update.session.stderr
    printed = sorted(v for v in values if v in output)
    assert not printed, f"{len(printed)} personal value(s) reached the session's output"


def test_the_refresh_logs_no_personal_value(observed):
    update, started, values = observed
    logged = [
        str(path.relative_to(update.machine.root))
        for path in pu.logs_written(update.machine.root, started)
        if any(v in path.read_text(encoding="utf-8", errors="replace") for v in values)
    ]
    assert not logged, f"logs holding a personal value: {logged}"
