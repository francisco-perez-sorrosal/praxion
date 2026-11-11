"""Behavioral tests for the hand path's instructions step and its terminal conversation.

The conversation runs over `io.StringIO` streams, the step over a `tmp_path` home and
plugin cache, and every identity is made up. The fixtures and helpers are the hook's own
test module's, as in the other install suites. Nothing here reaches the session's plugin
root, the real home or the machine's git identity.
"""

# ruff: noqa: F811 (a fixture's parameter name redefines the name it is imported under)
from __future__ import annotations

import ast
import io
import os
import shutil
import sys
from pathlib import Path

import pytest

# Fixtures are found by the name they are imported under, so each is imported though no code names it.
from test_auto_complete_install import (  # noqa: F401
    _CARRIED,
    _NEW_TEMPLATE,
    _TODAYS,
    HOOKS_DIR,
    REPO_ROOT,
    _fill,
    _link_instructions,
    _no_ambient_plugin_root,
    _previous_render,
    _render_module_reachable_by_the_hook_subprocess,
    _seed_template,
    fake_home,
    plugin_cache_dir,
    plugin_root,
    update,
)

# isort: split
# The suite's helper module puts scripts/ on sys.path; the hand path imports it by name.
import _install_hand_path as hand_path
import _install_refresh as refresh

INSTRUCTIONS = "~/.claude/CLAUDE.md"
_TYPED = {
    "USERNAME": "@tamsin-typed",
    "EMAIL": "tamsin.typed@example.invalid",
    "GITHUB_URL": "https://example.invalid/tamsin-typed",
}
_NOT_AS_ROOT = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores the permissions this breaks"
)


@pytest.fixture(autouse=True)
def _todays_identity(monkeypatch):
    """Today's derived identity is a made-up one, and the step never reaches the real git."""
    monkeypatch.setattr(update._render_mod, "derive_defaults", lambda: dict(_TODAYS))


@pytest.fixture
def installed(plugin_root):
    """The installed version's root, its template ready."""
    _seed_template(plugin_root, _NEW_TEMPLATE)
    return plugin_root


@pytest.fixture
def previous(fake_home):
    """The previous version's render, filled with the carried values."""
    return _previous_render(fake_home)


class Ran:
    """One run of `main` over string streams: its status and what each stream held."""

    def __init__(self, home: Path, root: Path, answers: str, environ=None):
        out, err = io.StringIO(), io.StringIO()
        self.status = hand_path.main(
            ["--root", str(root)],
            environ if environ is not None else {"HOME": str(home)},
            io.StringIO(answers),
            out,
            err,
        )
        self.out, self.err = out.getvalue(), err.getvalue()

    @property
    def line(self) -> str:
        assert self.out.endswith("\n"), self.out
        assert self.out.count("\n") == 1, self.out
        return self.out[:-1]


def _state(*paths: Path) -> list:
    """What each path holds, without following a link: text or bytes, inode, modification time."""
    state = []
    for path in paths:
        if not (path.is_symlink() or path.exists()):
            state.append(None)
            continue
        status = path.lstat()
        what = os.readlink(path) if path.is_symlink() else path.read_bytes()
        state.append((what, status.st_ino, status.st_mtime_ns))
    return state


def _link(home: Path) -> Path:
    return home / ".claude" / "CLAUDE.md"


def _ruin(render: Path) -> None:
    """Make `render` a file that no longer reads back as its template."""
    render.write_text(render.read_text(encoding="utf-8") + "A line added by hand.\n", "utf-8")


# -- A readable earlier render: carried forward ---------------------------------------------------


class TestCarryForward:
    @pytest.fixture
    def linked(self, fake_home, previous, installed):
        _link_instructions(fake_home, previous)
        return fake_home

    def test_the_offer_is_accepted_and_the_values_carried_without_a_question(
        self, linked, previous, installed
    ):
        ran = Ran(linked, installed, "1\n")

        assert _link(linked).read_text(encoding="utf-8") == _fill(_NEW_TEMPLATE, _CARRIED)
        assert os.path.realpath(_link(linked)) == str(installed / "claude/config/CLAUDE.md")
        assert "Username [" not in ran.err
        assert (ran.status, ran.line) == (
            0,
            f"{INSTRUCTIONS} set up (from version 9.9.8's values)",
        )

    def test_the_earlier_render_is_left_byte_identical(self, linked, previous, installed):
        before = _state(previous)

        Ran(linked, installed, "\n")

        assert _state(previous) == before

    def test_the_offer_says_which_version_the_instructions_were_rendered_from(
        self, linked, installed
    ):
        ran = Ran(linked, installed, "2\n")

        assert f"{INSTRUCTIONS} was rendered from version 9.9.8;" in ran.err

    def test_a_link_written_relative_to_the_claude_directory_is_followed(
        self, fake_home, previous, installed
    ):
        _link(fake_home).symlink_to(os.path.relpath(previous, _link(fake_home).parent))

        ran = Ran(fake_home, installed, "\n")

        assert ran.line == f"{INSTRUCTIONS} set up (from version 9.9.8's values)"

    def test_the_change_is_offered_before_anything_is_written(self, linked, previous, installed):
        before = _state(_link(linked), previous)

        ran = Ran(linked, installed, "2\n")

        assert _state(_link(linked), previous) == before
        assert not (installed / "claude/config/CLAUDE.md").exists()
        assert (ran.status, ran.line) == (
            3,
            f"{INSTRUCTIONS} skipped (run this command again, `install.sh code "
            "--complete-install`, and accept the instructions step)",
        )

    def test_a_placeholder_the_earlier_render_never_carried_gets_its_derived_value(
        self, fake_home, installed
    ):
        old = "user: {{USERNAME}}\nmail: {{EMAIL}}\n"
        render = _previous_render(fake_home, old)
        _link_instructions(fake_home, render)

        Ran(fake_home, installed, "\n")

        expected = _fill(_NEW_TEMPLATE, {**_CARRIED, "GITHUB_URL": _TODAYS["GITHUB_URL"]})
        assert _link(fake_home).read_text(encoding="utf-8") == expected

    def test_the_instructions_still_read_the_same_once_the_earlier_version_is_removed(
        self, linked, previous, installed
    ):
        Ran(linked, installed, "\n")
        shutil.rmtree(previous.parents[2])

        assert _link(linked).read_text(encoding="utf-8") == _fill(_NEW_TEMPLATE, _CARRIED)


# -- Instructions asked about: unreadable, missing ------------------------------------------------


class TestAskForValues:
    SKIPPED_LINE = (
        f"{INSTRUCTIONS} skipped (run this command again, `install.sh code "
        "--complete-install`, and accept the instructions step)"
    )

    def _unreadable(self, fake_home, previous):
        _ruin(previous)
        _link_instructions(fake_home, previous)

    def _answers(self, offer="1", values=("", "", ""), confirm=""):
        return "".join(f"{line}\n" for line in (offer, *values, confirm))

    def test_the_given_values_are_written_and_the_earlier_render_left_as_it_was(
        self, fake_home, previous, installed
    ):
        self._unreadable(fake_home, previous)
        ruined = _state(previous)
        answers = self._answers(values=tuple(_TYPED.values()))

        ran = Ran(fake_home, installed, answers)

        assert _link(fake_home).read_text(encoding="utf-8") == _fill(_NEW_TEMPLATE, _TYPED)
        assert _state(previous) == ruined
        assert (ran.status, ran.line) == (0, f"{INSTRUCTIONS} set up (with the values given)")

    @pytest.mark.parametrize(
        ("label", "key"),
        [("Username", "USERNAME"), ("Email", "EMAIL"), ("GitHub URL", "GITHUB_URL")],
    )
    def test_each_value_is_asked_with_todays_derived_value_as_its_default(
        self, fake_home, previous, installed, label, key
    ):
        self._unreadable(fake_home, previous)

        ran = Ran(fake_home, installed, self._answers())

        assert f"{label} [{_TODAYS[key]}]: " in ran.err

    def test_enter_at_each_prompt_renders_the_derived_values(self, fake_home, previous, installed):
        self._unreadable(fake_home, previous)

        Ran(fake_home, installed, self._answers())

        assert _link(fake_home).read_text(encoding="utf-8") == _fill(_NEW_TEMPLATE, _TODAYS)

    def test_the_values_to_write_are_shown_before_they_are_written(
        self, fake_home, previous, installed
    ):
        self._unreadable(fake_home, previous)

        ran = Ran(fake_home, installed, self._answers(values=tuple(_TYPED.values())))

        confirmation = ran.err[ran.err.rindex("The values to write") :]
        assert _TYPED["USERNAME"] in confirmation, confirmation
        assert _TYPED["EMAIL"] in confirmation, confirmation
        assert _TYPED["GITHUB_URL"] in confirmation, confirmation

    def test_n_at_the_confirmation_leaves_everything_as_it_was_and_names_it_skipped(
        self, fake_home, previous, installed
    ):
        self._unreadable(fake_home, previous)
        before = _state(_link(fake_home), previous)

        ran = Ran(fake_home, installed, self._answers(values=tuple(_TYPED.values()), confirm="n"))

        assert _state(_link(fake_home), previous) == before
        assert not (installed / "claude/config/CLAUDE.md").exists()
        assert ran.status == 3
        assert "skipped" in ran.line, ran.line

    def test_the_installed_versions_own_hand_edited_render_is_not_modified(
        self, fake_home, installed
    ):
        own = installed / "claude/config/CLAUDE.md"
        own.write_text(_fill(_NEW_TEMPLATE, _CARRIED) + "added by hand\n", encoding="utf-8")
        _link_instructions(fake_home, own)
        before = _state(own)

        ran = Ran(fake_home, installed, self._answers(values=tuple(_TYPED.values())))

        assert _state(own) == before
        assert _link(fake_home).read_text(encoding="utf-8") == _fill(_NEW_TEMPLATE, _TYPED)
        assert ran.status == 0

    def test_absent_instructions_are_set_up_with_the_given_values(self, fake_home, installed):
        ran = Ran(fake_home, installed, self._answers(values=tuple(_TYPED.values())))

        assert _link(fake_home).read_text(encoding="utf-8") == _fill(_NEW_TEMPLATE, _TYPED)
        assert ran.line == f"{INSTRUCTIONS} set up (with the values given)"

    def test_a_dangling_link_is_set_up_with_the_given_values(self, fake_home, installed):
        _link_instructions(fake_home, installed / "claude/config/CLAUDE.md")

        ran = Ran(fake_home, installed, self._answers(values=tuple(_TYPED.values())))

        assert _link(fake_home).read_text(encoding="utf-8") == _fill(_NEW_TEMPLATE, _TYPED)
        assert ran.line == f"{INSTRUCTIONS} set up (with the values given)"

    @pytest.mark.parametrize(
        "answers",
        [
            "",
            "1\n",
            "1\n\n",
            "1\n\n\n",
            "1\n\n\n\n",
        ],
        ids=["at-the-offer", "at-username", "at-email", "at-github", "at-the-confirmation"],
    )
    def test_the_input_ending_writes_nothing_and_is_no_answer(
        self, fake_home, previous, installed, answers
    ):
        self._unreadable(fake_home, previous)
        before = _state(_link(fake_home), previous)

        ran = Ran(fake_home, installed, answers)

        assert _state(_link(fake_home), previous) == before
        assert not (installed / "claude/config/CLAUDE.md").exists()
        assert (ran.status, ran.line) == (
            3,
            f"{INSTRUCTIONS} not set up: no answer (run the command again in your terminal)",
        )

    def test_the_input_ending_for_an_absent_link_creates_no_link(self, fake_home, installed):
        ran = Ran(fake_home, installed, "1\n\n")

        assert _state(_link(fake_home)) == [None]
        assert ran.status == 3

    def test_the_offer_for_an_unreadable_render_says_it_cannot_be_read_back(
        self, fake_home, previous, installed
    ):
        self._unreadable(fake_home, previous)

        assert "cannot be read back" in Ran(fake_home, installed, "").err

    def test_the_offer_for_missing_instructions_says_they_are_missing(self, fake_home, installed):
        assert "is missing" in Ran(fake_home, installed, "").err

    def test_declining_the_offer_for_an_unreadable_render_asks_nothing_and_writes_nothing(
        self, fake_home, previous, installed
    ):
        self._unreadable(fake_home, previous)
        before = _state(_link(fake_home), previous)

        ran = Ran(fake_home, installed, "2\n")

        assert _state(_link(fake_home), previous) == before
        assert not (installed / "claude/config/CLAUDE.md").exists()
        assert "Username [" not in ran.err
        assert (ran.status, ran.line) == (3, self.SKIPPED_LINE)

    def test_declining_the_offer_for_missing_instructions_asks_nothing_and_creates_no_link(
        self, fake_home, installed
    ):
        ran = Ran(fake_home, installed, "2\n")

        assert _state(_link(fake_home)) == [None]
        assert not (installed / "claude/config/CLAUDE.md").exists()
        assert "Username [" not in ran.err
        assert (ran.status, ran.line) == (3, self.SKIPPED_LINE)


# -- Current, not owned, checkout -----------------------------------------------------------------


class TestNoQuestion:
    def test_current_instructions_are_left_as_they_are_and_nothing_is_asked(
        self, fake_home, installed
    ):
        own = installed / "claude/config/CLAUDE.md"
        own.write_text(_fill(_NEW_TEMPLATE, _CARRIED), encoding="utf-8")
        _link_instructions(fake_home, own)
        before = _state(_link(fake_home), own)

        ran = Ran(fake_home, installed, "")  # a question would end the input and say so

        assert _state(_link(fake_home), own) == before
        assert ran.err == ""
        assert (ran.status, ran.line) == (0, f"{INSTRUCTIONS} current")

    def test_a_regular_file_is_left_alone_and_named_the_persons_own(self, fake_home, installed):
        _link(fake_home).write_text("my own instructions\n", encoding="utf-8")
        before = _state(_link(fake_home))

        ran = Ran(fake_home, installed, "")

        assert _state(_link(fake_home)) == before
        assert ran.err == ""
        assert (ran.status, ran.line) == (
            0,
            f"{INSTRUCTIONS} left alone: your own regular file",
        )

    def test_a_live_link_outside_the_cache_is_left_alone(self, fake_home, installed, tmp_path):
        clone = tmp_path / "clone" / "CLAUDE.md"
        clone.parent.mkdir()
        clone.write_text("a clone's render\n", encoding="utf-8")

        self._assert_left_alone(fake_home, installed, clone)

    def test_a_dangling_link_outside_the_cache_is_left_alone(self, fake_home, installed, tmp_path):
        self._assert_left_alone(fake_home, installed, tmp_path / "clone" / "CLAUDE.md")

    def _assert_left_alone(self, fake_home, installed, clone):
        _link_instructions(fake_home, clone)
        before = _state(_link(fake_home), clone)

        ran = Ran(fake_home, installed, "")

        assert _state(_link(fake_home), clone) == before
        assert ran.err == ""
        assert (ran.status, ran.line) == (
            0,
            f"{INSTRUCTIONS} left alone: a link outside the plugin cache that its own "
            "`install.sh code` sets up",
        )

    @pytest.fixture
    def checkout(self, tmp_path):
        checkout = tmp_path / "checkout"
        _seed_template(checkout, _NEW_TEMPLATE)
        return checkout

    def test_a_checkout_leaves_absent_instructions_alone_and_names_its_own_installer(
        self, fake_home, previous, checkout
    ):
        self._assert_checkout_leaves_alone(fake_home, previous, checkout)

    def test_a_checkout_leaves_a_cache_render_alone_and_names_its_own_installer(
        self, fake_home, previous, checkout
    ):
        _link_instructions(fake_home, previous)

        self._assert_checkout_leaves_alone(fake_home, previous, checkout)

    def _assert_checkout_leaves_alone(self, fake_home, previous, checkout):
        before = _state(_link(fake_home), previous)

        ran = Ran(fake_home, checkout, "")

        assert _state(_link(fake_home), previous) == before
        assert ran.err == ""
        assert ran.status == 3
        assert ran.line == (
            f"{INSTRUCTIONS} left alone: this command runs from a checkout "
            f'(run "{checkout}/install.sh" code there)'
        )

    def test_a_checkout_still_names_a_regular_file_the_persons_own(self, fake_home, tmp_path):
        _link(fake_home).write_text("mine\n", encoding="utf-8")

        ran = Ran(fake_home, tmp_path / "checkout", "")

        assert ran.status == 0
        assert "your own regular file" in ran.line, ran.line


# -- Failures ---------------------------------------------------------------------------------------


class TestFailures:
    def _setup(self, fake_home, previous):
        _link_instructions(fake_home, previous)
        return _state(_link(fake_home), previous)

    @_NOT_AS_ROOT
    def test_an_unwritable_render_directory_is_a_permission_failure_and_keeps_the_link(
        self, fake_home, previous, installed
    ):
        before = self._setup(fake_home, previous)
        config = installed / "claude/config"
        config.chmod(0o555)
        try:
            ran = Ran(fake_home, installed, "\n")
        finally:
            config.chmod(0o755)

        assert _state(_link(fake_home), previous) == before
        assert (ran.status, ran.line) == (
            1,
            f"{INSTRUCTIONS} could not be set up (permission denied; "
            "run `/praxion-complete-install` again)",
        )

    def test_a_missing_template_is_a_reading_failure(self, fake_home, previous, installed):
        before = self._setup(fake_home, previous)
        (installed / "claude/config/CLAUDE.md.tmpl").unlink()

        ran = Ran(fake_home, installed, "\n")

        assert _state(_link(fake_home), previous) == before
        assert (ran.status, ran.line) == (
            1,
            f"{INSTRUCTIONS} could not be set up (could not read the earlier render or the "
            "template; run `/praxion-complete-install` again)",
        )

    def test_a_render_slot_that_cannot_be_replaced_is_a_writing_failure(
        self, fake_home, previous, installed
    ):
        before = self._setup(fake_home, previous)
        (installed / "claude/config/CLAUDE.md").mkdir()

        ran = Ran(fake_home, installed, "\n")

        assert _state(_link(fake_home), previous) == before
        assert (ran.status, ran.line) == (
            1,
            f"{INSTRUCTIONS} could not be set up (could not write the new render or the link; "
            "run `/praxion-complete-install` again)",
        )

    @pytest.mark.parametrize("error", [OSError, PermissionError, RuntimeError, ValueError])
    def test_an_exception_message_never_reaches_the_line_or_the_output(
        self, fake_home, previous, installed, monkeypatch, error
    ):
        self._setup(fake_home, previous)
        secret = _TYPED["EMAIL"]

        def refuse(*_args, **_kwargs):
            raise error(secret)

        monkeypatch.setattr(hand_path, "write_instructions", refuse)

        ran = Ran(fake_home, installed, "\n")

        assert secret not in ran.out + ran.err
        assert ran.status == 1
        assert ran.line.startswith(f"{INSTRUCTIONS} could not be set up ("), ran.line

    def test_an_unexpected_exception_anywhere_is_named_unexpected(
        self, fake_home, installed, monkeypatch
    ):
        def explode(*_args, **_kwargs):
            raise RuntimeError(_TYPED["USERNAME"])

        monkeypatch.setattr(hand_path, "run_instructions_step", explode)

        ran = Ran(fake_home, installed, "")

        assert _TYPED["USERNAME"] not in ran.out + ran.err
        assert ran.status == 1
        assert "unexpected error" in ran.line, ran.line

    @pytest.mark.parametrize("home", ["", "relative/home"])
    def test_a_home_that_is_not_absolute_changes_nothing_and_fails(
        self, tmp_path, installed, monkeypatch, home
    ):
        monkeypatch.chdir(tmp_path)

        ran = Ran(Path(home), installed, "1\n\n\n\n", environ={"HOME": home})

        assert ran.status == 1
        assert not (tmp_path / ".claude").exists()
        assert not (tmp_path / "relative").exists()

    def test_a_missing_root_argument_is_a_usage_error(self):
        with pytest.raises(SystemExit) as exited:
            hand_path.main([], {"HOME": "/"}, io.StringIO(), io.StringIO(), io.StringIO())

        assert exited.value.code == 2

    def test_no_home_in_the_environment_fails(self, installed):
        ran = Ran(Path("/"), installed, "", environ={})

        assert ran.status == 1
        assert "unexpected error" in ran.line, ran.line


# -- The line and the status of every outcome -----------------------------------------------------

_EVERY_OUTCOME = [
    (refresh.SetUp(), 0),
    (refresh.Current(), 0),
    (refresh.LeftAlone(refresh.LeaveAloneReason.OWN_FILE), 0),
    (refresh.LeftAlone(refresh.LeaveAloneReason.OUTSIDE_CACHE), 0),
    (refresh.LeftAlone(refresh.LeaveAloneReason.CHECKOUT), 3),
    (refresh.Skipped(refresh.SkipPoint.OFFER), 3),
    (refresh.Skipped(refresh.SkipPoint.CONFIRM), 3),
    (refresh.NoAnswer(), 3),
    *((refresh.Failed(kind), 1) for kind in refresh.FailureKind),
]


@pytest.mark.parametrize(("outcome", "status"), _EVERY_OUTCOME, ids=repr)
def test_every_outcome_prints_one_line_and_exits_with_its_status(
    outcome, status, installed, tmp_path, monkeypatch
):
    monkeypatch.setattr(hand_path, "run_instructions_step", lambda *_: (outcome, None))

    ran = Ran(tmp_path, installed, "")

    assert ran.status == status
    assert ran.out == hand_path.outcome_line(outcome, str(installed), None) + "\n"
    assert ran.line.startswith(f"{INSTRUCTIONS} ")
    assert ran.err == ""


_HOW_TO_FINISH = [
    (refresh.Skipped(refresh.SkipPoint.OFFER), "--complete-install"),
    (refresh.Skipped(refresh.SkipPoint.CONFIRM), "--complete-install"),
    (refresh.NoAnswer(), "run the command again"),
    (refresh.LeftAlone(refresh.LeaveAloneReason.CHECKOUT), '"/some/root/install.sh" code'),
    *((refresh.Failed(kind), "/praxion-complete-install") for kind in refresh.FailureKind),
]


@pytest.mark.parametrize(("outcome", "words"), _HOW_TO_FINISH, ids=repr)
def test_a_line_that_leaves_the_instructions_unfinished_says_how_to_finish(outcome, words):
    assert words in hand_path.outcome_line(outcome, "/some/root", None)


def test_every_failure_kind_has_words_and_none_carries_a_message():
    assert set(hand_path._FAILURE_DETAIL) == set(refresh.FailureKind)


# -- The identity goes only into the render -------------------------------------------------------


def _files_holding(root: Path, value: str) -> list[Path]:
    needle = value.encode()
    return sorted(
        p
        for p in root.rglob("*")
        if p.is_file() and not p.is_symlink() and needle in p.read_bytes()
    )


def test_a_given_value_is_in_the_render_and_nowhere_else_not_even_standard_output(
    fake_home, previous, installed, tmp_path
):
    _ruin(previous)
    _link_instructions(fake_home, previous)

    ran = Ran(fake_home, installed, "1\n" + "".join(f"{v}\n" for v in _TYPED.values()) + "\n")

    render = installed / "claude/config/CLAUDE.md"
    assert _files_holding(tmp_path, _TYPED["USERNAME"]) == [render]
    assert _files_holding(tmp_path, _TYPED["EMAIL"]) == [render]
    assert _TYPED["USERNAME"] not in ran.out, ran.out
    assert _TYPED["EMAIL"] not in ran.out, ran.out
    assert _TYPED["GITHUB_URL"] not in ran.out, ran.out


# -- Python 3.9 -------------------------------------------------------------------------------------

_HAND_PATH_MODULES = (
    HOOKS_DIR / "_install_hand_path.py",
    HOOKS_DIR / "_install_refresh.py",
    HOOKS_DIR / "_install_update.py",
    REPO_ROOT / "scripts" / "render_claude_md.py",
)


@pytest.mark.parametrize("module", _HAND_PATH_MODULES, ids=lambda p: p.name)
def test_every_module_the_hand_path_imports_parses_as_python_3_9(module):
    ast.parse(module.read_text(encoding="utf-8"), filename=str(module), feature_version=(3, 9))


def test_the_hand_path_imports_only_the_standard_library_and_its_siblings():
    tree = ast.parse(_HAND_PATH_MODULES[0].read_text(encoding="utf-8"))
    imported = {
        node.module.split(".")[0] if isinstance(node, ast.ImportFrom) else alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in (node.names if isinstance(node, ast.Import) else [None])
    }

    # `mutmut` is what the mutation sensor injects into the copy it runs this module from.
    allowed = set(sys.stdlib_module_names) | {"_install_refresh", "_install_update", "mutmut"}
    assert imported <= allowed
