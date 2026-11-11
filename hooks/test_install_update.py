"""Behavioral tests for hooks/_install_update.py -- the effects of the auto-complete
hook's update path: the script and rule refreshes, the instructions snapshot and
the dispatcher that orders them.

The fixtures, plugin layout and helpers are the hook's own test module's; this
module imports them so the two suites lay out one plugin and one HOME the same way.
"""

# ruff: noqa: F401, F811 (a fixture imported by name is found by its parameter name, which redefines it)
from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent
# The mutation sensor runs a copy of this directory one level down, so `scripts/`
# (home of `render_claude_md`) is found from the nearest ancestor that holds it.
_SCRIPTS_DIR = next(
    p / "scripts" for p in HOOKS_DIR.parents if (p / "scripts" / "render_claude_md.py").is_file()
)
sys.path[:0] = [str(HOOKS_DIR), str(_SCRIPTS_DIR)]
import _install_update as update  # noqa: E402 (after sys.path injection)
from _install_refresh import (  # noqa: E402 (after sys.path injection)
    BinEntry,
    EntryKind,
    InstructionsSnapshot,
    Keep,
    Link,
    Remove,
    Repoint,
    SnapshotKind,
)
from test_auto_complete_install import (  # noqa: E402 (after sys.path injection)
    _CARRIED,
    _NEW_TEMPLATE,
    _TODAYS,
    _cached_version,
    _fake_home_module,
    _no_ambient_plugin_root,
    _plant_link,
    _rule_links,
    _seed_script,
    _seed_template,
    claude_md_symlink,
    fake_home,
    marker_path,
    plugin_cache_dir,
    plugin_root,
    rules_sentinel,
)


@pytest.fixture(autouse=True)
def _no_ambient_home(monkeypatch, tmp_path):
    """No test reads the operator's own HOME: the git identity derivation does."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


class TestRuleUpdate:
    """On the update path a rule link into another cached version moves to this one."""

    @staticmethod
    def _previous_version_rule(plugin_root: Path, rel: str) -> Path:
        previous = plugin_root.parent / "9.9.8" / "rules" / rel
        previous.parent.mkdir(parents=True)
        previous.write_text("# the rule, as the previous version linked it\n", encoding="utf-8")
        return previous

    def test_repoints_a_live_link_into_the_previous_version(self, fake_home, plugin_root):
        rel = "swe/coding-style.md"
        _plant_link(fake_home, rel, self._previous_version_rule(plugin_root, rel))

        update._update_rules(fake_home, plugin_root)

        assert _rule_links(fake_home)[rel] == (plugin_root / "rules" / rel).resolve()

    def test_leaves_a_live_link_into_a_checkout_as_it_is(self, fake_home, plugin_root, tmp_path):
        checkout_rule = tmp_path / "checkout" / "rules" / "swe" / "coding-style.md"
        checkout_rule.parent.mkdir(parents=True)
        checkout_rule.write_text("# coding style, from a clone install\n", encoding="utf-8")
        _plant_link(fake_home, "swe/coding-style.md", checkout_rule)

        update._update_rules(fake_home, plugin_root)

        assert _rule_links(fake_home)["swe/coding-style.md"] == checkout_rule.resolve()

    def test_still_sweeps_and_links_as_the_refresh_does(self, fake_home, plugin_root):
        stale_rel = "swe/agent-model-routing-resident.md"
        stale = _plant_link(
            fake_home, stale_rel, self._previous_version_rule(plugin_root, stale_rel)
        )

        update._update_rules(fake_home, plugin_root)

        assert not stale.is_symlink()
        assert "swe/coding-style.md" in _rule_links(fake_home)

    def test_the_refresh_alone_leaves_a_live_link_into_another_version(
        self, fake_home, plugin_root, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        rel = "swe/coding-style.md"
        previous = self._previous_version_rule(plugin_root, rel)
        _plant_link(fake_home, rel, previous)

        module._refresh_rules(fake_home, plugin_root)

        # The flow for a root that is not a cache version never re-points a live link.
        assert _rule_links(fake_home)[rel] == previous.resolve()

    def test_a_single_function_runs_as_it_did(self, fake_home, plugin_root, monkeypatch):
        module = _fake_home_module(monkeypatch, fake_home)

        module._run_rule_linker(fake_home, plugin_root, "link_rules")

        assert "swe/coding-style.md" in _rule_links(fake_home)

    def test_the_first_failing_function_ends_the_sequence_and_raises(self, fake_home, plugin_root):
        with pytest.raises(subprocess.CalledProcessError):
            update._run_rule_linkers(fake_home, plugin_root, ("no_such_function", "link_rules"))

        assert _rule_links(fake_home) == {}


def _refuse(*_args):
    raise PermissionError("refused")


class TestOfferedScripts:
    def test_names_the_executable_user_facing_scripts_with_their_paths(
        self, fake_home, plugin_root
    ):
        script = _seed_script(plugin_root / "scripts", "praxion-dashboard")

        offered = update.offered_scripts(plugin_root)

        assert [(o.name, o.path) for o in offered] == [("praxion-dashboard", str(script))]

    @pytest.mark.parametrize(
        ("name", "executable"),
        [
            ("helper.py", False),
            ("merge_driver_observations.py", True),
            ("post-merge-hook.sh", True),
        ],
    )
    def test_leaves_out_what_the_operator_does_not_run(
        self, fake_home, plugin_root, name, executable
    ):
        _seed_script(plugin_root / "scripts", name, executable=executable)

        assert update.offered_scripts(plugin_root) == ()

    def test_leaves_out_a_directory(self, fake_home, plugin_root):
        (plugin_root / "scripts" / "praxion-tools").mkdir(mode=0o755)

        assert update.offered_scripts(plugin_root) == ()

    def test_a_plugin_without_scripts_offers_none(self, fake_home, plugin_root):
        plugin_root.joinpath("scripts").rmdir()

        assert update.offered_scripts(plugin_root) == ()


class TestSnapshotBin:
    def test_tells_a_link_a_file_and_another_kind_apart(self, fake_home):
        bin_dir = fake_home / ".local" / "bin"
        target = fake_home / "target-tool"
        target.write_text("#!/bin/sh\n", encoding="utf-8")
        (bin_dir / "linked").symlink_to(target)
        (bin_dir / "plain").write_text("mine\n", encoding="utf-8")
        (bin_dir / "folder").mkdir()

        kinds = {entry.name: entry.kind for entry in update.snapshot_bin(bin_dir)}

        assert kinds == {
            "linked": EntryKind.LINK,
            "plain": EntryKind.FILE,
            "folder": EntryKind.OTHER,
        }

    def test_a_link_carries_its_text_and_its_real_path(self, fake_home):
        bin_dir = fake_home / ".local" / "bin"
        target = fake_home / "target-tool"
        target.write_text("#!/bin/sh\n", encoding="utf-8")
        (bin_dir / "linked").symlink_to(target)

        (entry,) = update.snapshot_bin(bin_dir)

        assert (entry.text, entry.real) == (str(target), str(target.resolve()))

    def test_a_dangling_link_has_no_real_path(self, fake_home):
        bin_dir = fake_home / ".local" / "bin"
        (bin_dir / "orphan").symlink_to(fake_home / "removed-tool")

        (entry,) = update.snapshot_bin(bin_dir)

        assert (entry.kind, entry.text, entry.real) == (
            EntryKind.LINK,
            str(fake_home / "removed-tool"),
            None,
        )

    def test_a_file_and_another_kind_carry_no_link_data(self, fake_home):
        bin_dir = fake_home / ".local" / "bin"
        (bin_dir / "plain").write_text("mine\n", encoding="utf-8")
        (bin_dir / "folder").mkdir()

        entries = {entry.name: entry for entry in update.snapshot_bin(bin_dir)}

        assert entries == {
            "plain": BinEntry("plain", EntryKind.FILE, "", None),
            "folder": BinEntry("folder", EntryKind.OTHER, "", None),
        }

    def test_a_missing_directory_has_no_entries(self, fake_home):
        assert update.snapshot_bin(fake_home / "nowhere") == ()


class TestRefreshScripts:
    def test_a_cache_link_is_repointed_to_the_offered_script(self, fake_home, plugin_root):
        old_root = _cached_version(fake_home, "0.1.0")
        script = _seed_script(plugin_root / "scripts", "praxion-dashboard")
        dest = fake_home / ".local" / "bin" / "praxion-dashboard"
        dest.symlink_to(_seed_script(old_root / "scripts", "praxion-dashboard"))

        update.refresh_scripts(fake_home, plugin_root)

        assert os.readlink(dest) == str(script)

    def test_a_relative_cache_link_is_repointed_too(self, fake_home, plugin_root):
        old_root = _cached_version(fake_home, "0.1.0")
        _seed_script(old_root / "scripts", "praxion-dashboard")
        script = _seed_script(plugin_root / "scripts", "praxion-dashboard")
        dest = fake_home / ".local" / "bin" / "praxion-dashboard"
        dest.symlink_to(os.path.relpath(old_root / "scripts" / "praxion-dashboard", dest.parent))

        update.refresh_scripts(fake_home, plugin_root)

        assert os.readlink(dest) == str(script)

    def test_a_repointed_link_outlives_the_removal_of_the_old_version(self, fake_home, plugin_root):
        old_root = _cached_version(fake_home, "0.1.0")
        dest = fake_home / ".local" / "bin" / "praxion-dashboard"
        dest.symlink_to(_seed_script(old_root / "scripts", "praxion-dashboard"))
        _seed_script(plugin_root / "scripts", "praxion-dashboard")

        update.refresh_scripts(fake_home, plugin_root)
        shutil.rmtree(old_root)

        assert dest.exists()

    def test_a_cache_link_for_a_dropped_script_is_removed(self, fake_home, plugin_root):
        old_root = _cached_version(fake_home, "0.1.0")
        dest = fake_home / ".local" / "bin" / "retired-tool"
        dest.symlink_to(_seed_script(old_root / "scripts", "retired-tool"))

        update.refresh_scripts(fake_home, plugin_root)

        assert not dest.is_symlink()

    def test_a_free_name_is_linked_and_the_directory_created(self, fake_home, plugin_root):
        script = _seed_script(plugin_root / "scripts", "praxion-dashboard")
        (fake_home / ".local" / "bin").rmdir()
        (fake_home / ".local").rmdir()

        update.refresh_scripts(fake_home, plugin_root)

        assert os.readlink(fake_home / ".local" / "bin" / "praxion-dashboard") == str(script)

    def test_a_regular_file_and_a_clone_link_are_left_as_they_were(
        self, fake_home, plugin_root, tmp_path
    ):
        _seed_script(plugin_root / "scripts", "praxion-dashboard")
        _seed_script(plugin_root / "scripts", "praxion-status")
        bin_dir = fake_home / ".local" / "bin"
        own = bin_dir / "praxion-dashboard"
        own.write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
        clone_tool = _seed_script(tmp_path / "clone" / "praxion" / "scripts", "praxion-status")
        clone_link = bin_dir / "praxion-status"
        clone_link.symlink_to(clone_tool)

        def observe():
            return (
                own.read_bytes(),
                own.lstat().st_ino,
                os.readlink(clone_link),
                clone_link.lstat().st_ino,
            )

        before = observe()
        update.refresh_scripts(fake_home, plugin_root)

        assert observe() == before

    def test_a_link_already_to_the_offered_script_keeps_its_inode(self, fake_home, plugin_root):
        script = _seed_script(plugin_root / "scripts", "praxion-dashboard")
        dest = fake_home / ".local" / "bin" / "praxion-dashboard"
        dest.symlink_to(script)
        inode = dest.lstat().st_ino

        update.refresh_scripts(fake_home, plugin_root)

        assert dest.lstat().st_ino == inode


class TestApplyScriptActions:
    def test_every_action_is_applied_and_the_first_error_raised_after_the_loop(
        self, fake_home, monkeypatch
    ):
        bin_dir = fake_home / ".local" / "bin"
        tool = fake_home / "tool"
        (bin_dir / "stale").symlink_to(tool)
        (bin_dir / "own").write_text("mine\n", encoding="utf-8")
        actions = (
            Repoint("stale", "/elsewhere"),
            Link("own", str(tool)),
            Link("fresh", str(tool)),
        )
        monkeypatch.setattr(os, "replace", _refuse)

        with pytest.raises(PermissionError):
            update.apply_script_actions(bin_dir, actions)

        assert os.readlink(bin_dir / "fresh") == str(tool)

    def test_a_link_gone_before_its_removal_is_not_an_error(self, fake_home, monkeypatch):
        monkeypatch.setattr(Path, "is_symlink", lambda _self: True)

        update.apply_script_actions(fake_home / ".local" / "bin", (Remove("gone"),))

    def test_a_failed_repoint_raises_its_own_error_when_the_temporary_link_is_already_gone(
        self, fake_home, monkeypatch
    ):
        bin_dir = fake_home / ".local" / "bin"
        (bin_dir / "stale").symlink_to(fake_home / "tool")

        def lose_the_temporary_then_refuse(temporary, _destination):
            Path(temporary).unlink()
            raise PermissionError("refused")

        monkeypatch.setattr(os, "replace", lose_the_temporary_then_refuse)

        with pytest.raises(PermissionError):
            update.apply_script_actions(bin_dir, (Repoint("stale", "/elsewhere"),))

    def test_a_failed_repoint_leaves_the_old_link_and_no_temporary_link(
        self, fake_home, monkeypatch
    ):
        bin_dir = fake_home / ".local" / "bin"
        tool = fake_home / "tool"
        (bin_dir / "stale").symlink_to(tool)
        monkeypatch.setattr(os, "replace", _refuse)

        with pytest.raises(PermissionError):
            update.apply_script_actions(bin_dir, (Repoint("stale", "/elsewhere"),))

        assert sorted(p.name for p in bin_dir.iterdir()) == ["stale"]
        assert os.readlink(bin_dir / "stale") == str(tool)

    def test_a_successful_repoint_leaves_no_temporary_link(self, fake_home):
        bin_dir = fake_home / ".local" / "bin"
        (bin_dir / "stale").symlink_to(fake_home / "tool")

        update.apply_script_actions(bin_dir, (Repoint("stale", "/elsewhere"),))

        assert sorted(p.name for p in bin_dir.iterdir()) == ["stale"]
        assert os.readlink(bin_dir / "stale") == "/elsewhere"

    def test_remove_unlinks_a_link_only(self, fake_home):
        bin_dir = fake_home / ".local" / "bin"
        own = bin_dir / "own"
        own.write_text("mine\n", encoding="utf-8")
        (bin_dir / "stale").symlink_to(fake_home / "tool")

        update.apply_script_actions(bin_dir, (Remove("own"), Remove("stale")))

        assert own.read_text(encoding="utf-8") == "mine\n"
        assert not (bin_dir / "stale").is_symlink()

    def test_remove_of_a_missing_name_is_not_an_error(self, fake_home):
        update.apply_script_actions(fake_home / ".local" / "bin", (Remove("gone"),))

    def test_link_never_overwrites_what_sits_under_its_name(self, fake_home):
        bin_dir = fake_home / ".local" / "bin"
        own = bin_dir / "own"
        own.write_text("mine\n", encoding="utf-8")

        with pytest.raises(FileExistsError):
            update.apply_script_actions(bin_dir, (Link("own", "/elsewhere"),))

        assert own.read_text(encoding="utf-8") == "mine\n"

    def test_keep_does_nothing(self, fake_home):
        bin_dir = fake_home / ".local" / "bin"
        link = bin_dir / "kept"
        link.symlink_to(fake_home / "tool")
        inode = link.lstat().st_ino

        update.apply_script_actions(bin_dir, (Keep("kept"),))

        assert link.lstat().st_ino == inode


class TestUpdatePath:
    """A re-armed run from a cache version directory refreshes, quietly and fail-open."""

    @pytest.fixture
    def armed(self, fake_home, plugin_cache_dir, marker_path, claude_md_symlink, rules_sentinel):
        """Surfaces installed, completion marker present but older than the cache."""
        marker_path.write_text("")
        os.utime(marker_path, (1_000_000, 1_000_000))
        os.utime(plugin_cache_dir, (2_000_000, 2_000_000))
        return fake_home

    @staticmethod
    def _recording_steps(
        monkeypatch, calls: list, fail: dict | None = None, arguments: list | None = None
    ):
        def _step(name: str):
            def run(home: Path, root: Path) -> None:
                calls.append(name)
                if arguments is not None:
                    arguments.append((home, root))
                if fail and name in fail:
                    raise fail[name]

            return run

        monkeypatch.setattr(update, "_UPDATE_STEPS", (_step("first"), _step("second")))

    def _run_hook(self, module, monkeypatch) -> list[str]:
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
        lines: list[str] = []
        module._run(lines)
        return lines

    def test_the_steps_are_the_instructions_then_the_rules_then_the_scripts(self, fake_home):
        assert update._UPDATE_STEPS == (
            update._update_instructions,
            update._update_rules,
            update.refresh_scripts,
        )

    def test_a_marked_cache_install_with_surfaces_runs_the_update_steps(self, armed, monkeypatch):
        module = _fake_home_module(monkeypatch, armed)
        calls: list = []
        self._recording_steps(monkeypatch, calls)

        self._run_hook(module, monkeypatch)

        assert calls == ["first", "second"]

    def test_each_step_receives_the_home_and_the_plugin_root(self, armed, plugin_root, monkeypatch):
        module = _fake_home_module(monkeypatch, armed)
        arguments: list = []
        self._recording_steps(monkeypatch, [], arguments=arguments)

        self._run_hook(module, monkeypatch)

        assert arguments == [(armed, plugin_root)] * 2

    def test_a_checkout_root_never_reaches_the_update_path(self, armed, tmp_path, monkeypatch):
        module = _fake_home_module(monkeypatch, armed)
        checkout = tmp_path / "checkout"
        checkout.mkdir()
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(checkout))
        calls: list = []
        self._recording_steps(monkeypatch, calls)

        self._run_hook(module, monkeypatch)

        assert calls == []

    def test_a_first_install_without_a_marker_never_reaches_the_update_path(
        self, armed, marker_path, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, armed)
        marker_path.unlink()
        calls: list = []
        self._recording_steps(monkeypatch, calls)

        self._run_hook(module, monkeypatch)

        assert calls == []

    def test_a_cache_root_with_a_marker_reaches_the_update_path_whatever_the_surfaces(
        self, armed, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, armed)
        (armed / ".claude" / "CLAUDE.md").unlink()
        calls: list = []
        self._recording_steps(monkeypatch, calls)

        self._run_hook(module, monkeypatch)

        assert calls == ["first", "second"]

    def test_a_checkout_root_with_a_marker_and_missing_surfaces_keeps_the_cold_path(
        self, armed, tmp_path, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, armed)
        checkout = tmp_path / "checkout"
        _seed_template(checkout)
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(checkout))
        monkeypatch.setenv("PRAXION_AUTO_COMPLETE", "1")
        (armed / ".claude" / "CLAUDE.md").unlink()
        calls: list = []
        self._recording_steps(monkeypatch, calls)

        self._run_hook(module, monkeypatch)

        assert calls == []
        assert os.readlink(armed / ".claude" / "CLAUDE.md") == str(
            checkout / "claude" / "config" / "CLAUDE.md"
        )

    def test_a_failing_step_does_not_stop_the_next_one(self, armed, monkeypatch):
        module = _fake_home_module(monkeypatch, armed)
        calls: list = []
        self._recording_steps(monkeypatch, calls, fail={"first": OSError("disk")})

        self._run_hook(module, monkeypatch)

        assert calls == ["first", "second"]

    def test_a_failure_prints_one_line_with_the_exception_type_only(
        self, armed, monkeypatch, capsys
    ):
        module = _fake_home_module(monkeypatch, armed)
        secret = "/home/someone/private-value"
        self._recording_steps(monkeypatch, [], fail={"first": PermissionError(secret)})

        lines = self._run_hook(module, monkeypatch)

        assert capsys.readouterr() == ("", "")
        assert lines == [
            "[Praxion] Update refresh could not finish (PermissionError); "
            "run /praxion-complete-install to complete it."
        ]

    def test_the_first_of_several_failures_is_the_one_reported(self, armed, monkeypatch):
        module = _fake_home_module(monkeypatch, armed)
        fail = {"first": KeyError("a"), "second": OSError("b")}
        self._recording_steps(monkeypatch, [], fail=fail)

        lines = self._run_hook(module, monkeypatch)

        assert [line.count("(KeyError)") for line in lines] == [1]

    def test_the_marker_is_rewritten_after_a_failure(self, armed, marker_path, monkeypatch):
        module = _fake_home_module(monkeypatch, armed)
        self._recording_steps(monkeypatch, [], fail={"first": OSError("disk")})

        self._run_hook(module, monkeypatch)

        assert marker_path.stat().st_mtime > 1_000_000

    def test_a_fully_successful_run_prints_nothing(self, armed, monkeypatch, capsys):
        module = _fake_home_module(monkeypatch, armed)
        self._recording_steps(monkeypatch, [])

        lines = self._run_hook(module, monkeypatch)

        assert (lines, capsys.readouterr()) == ([], ("", ""))

    def test_an_unwritable_marker_after_a_failure_still_reports_the_failure(
        self, armed, marker_path, monkeypatch
    ):
        marker_path.unlink()
        marker_path.mkdir()
        self._recording_steps(monkeypatch, [], fail={"second": OSError("disk")})

        lines = update._run_update_path(armed, armed)

        assert [line.count("(OSError)") for line in lines] == [1]


class TestSnapshotInstructions:
    def test_a_missing_entry_is_absent(self, tmp_path):
        snapshot = update.snapshot_instructions(tmp_path / "CLAUDE.md")

        assert snapshot == InstructionsSnapshot(SnapshotKind.ABSENT, "", False)

    def test_a_regular_file_is_a_file(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text("# mine\n", encoding="utf-8")

        snapshot = update.snapshot_instructions(tmp_path / "CLAUDE.md")

        assert snapshot == InstructionsSnapshot(SnapshotKind.FILE, "", False)

    def test_a_directory_is_another_kind(self, tmp_path):
        (tmp_path / "CLAUDE.md").mkdir()

        snapshot = update.snapshot_instructions(tmp_path / "CLAUDE.md")

        assert snapshot == InstructionsSnapshot(SnapshotKind.OTHER, "", False)

    def test_a_live_link_carries_its_text_and_resolves(self, tmp_path):
        (tmp_path / "render.md").write_text("# render\n", encoding="utf-8")
        (tmp_path / "CLAUDE.md").symlink_to("render.md")

        snapshot = update.snapshot_instructions(tmp_path / "CLAUDE.md")

        assert snapshot == InstructionsSnapshot(SnapshotKind.LINK, "render.md", True)

    def test_a_dangling_link_carries_its_text_and_does_not_resolve(self, tmp_path):
        (tmp_path / "CLAUDE.md").symlink_to("gone.md")

        snapshot = update.snapshot_instructions(tmp_path / "CLAUDE.md")

        assert snapshot == InstructionsSnapshot(SnapshotKind.LINK, "gone.md", False)


class TestDefaultsForMissingKeys:
    """Which keys need a default, and how defaults join the carried values: no effects."""

    def test_the_missing_keys_are_the_template_names_not_carried(self):
        carried = {"USERNAME": "@first-person"}

        missing = update._missing_keys("{{USERNAME}} {{EMAIL}} {{EMAIL}} {{SHELL_NAME}}", carried)

        assert missing == {"EMAIL", "SHELL_NAME"}

    def test_nothing_is_missing_when_every_template_key_was_carried(self):
        assert update._missing_keys(_NEW_TEMPLATE, _CARRIED) == frozenset()

    def test_a_default_fills_only_a_missing_key_and_never_a_carried_one(self):
        carried = {"USERNAME": _CARRIED["USERNAME"]}

        values = update._with_defaults(carried, frozenset({"EMAIL"}), _TODAYS)

        assert values == {"USERNAME": _CARRIED["USERNAME"], "EMAIL": _TODAYS["EMAIL"]}

    def test_a_missing_key_without_a_default_stays_out(self):
        values = update._with_defaults(_CARRIED, frozenset({"SHELL_NAME"}), _TODAYS)

        assert values == _CARRIED


def _dangling_cache_link(home: Path) -> Path:
    """~/.claude/CLAUDE.md as a link into a removed cached version's render."""
    gone = _cached_version(home, "9.9.8") / "claude" / "config" / "CLAUDE.md"
    link = home / ".claude" / "CLAUDE.md"
    link.symlink_to(gone)
    return link


class TestInstructionStates:
    """Each of the five states of ~/.claude/CLAUDE.md reaches its own action."""

    @pytest.fixture(autouse=True)
    def _asks_nothing(self, monkeypatch):
        monkeypatch.setenv("PRAXION_AUTO_COMPLETE", "1")

    def test_a_regular_file_is_left_byte_identical(self, fake_home, plugin_root):
        _seed_template(plugin_root)
        mine = fake_home / ".claude" / "CLAUDE.md"
        mine.write_text("# my own notes\n", encoding="utf-8")
        before = (mine.read_bytes(), mine.stat().st_ino)

        update._update_instructions(fake_home, plugin_root)

        assert (mine.read_bytes(), mine.stat().st_ino) == before

    def test_a_link_outside_the_cache_is_left_where_it_points(
        self, fake_home, plugin_root, tmp_path
    ):
        _seed_template(plugin_root)
        clone_render = tmp_path / "clone" / "claude" / "config" / "CLAUDE.md"
        clone_render.parent.mkdir(parents=True)
        clone_render.write_text("# the clone's render\n", encoding="utf-8")
        link = fake_home / ".claude" / "CLAUDE.md"
        link.symlink_to(clone_render)

        update._update_instructions(fake_home, plugin_root)

        assert os.readlink(link) == str(clone_render)

    def test_a_dangling_cache_link_is_set_up_as_a_first_install_sets_it_up(
        self, fake_home, plugin_root, monkeypatch
    ):
        _seed_template(plugin_root)
        link = _dangling_cache_link(fake_home)
        monkeypatch.setattr(update._render_mod, "derive_defaults", lambda: dict(_TODAYS))

        update._update_instructions(fake_home, plugin_root)

        assert os.readlink(link) == str(plugin_root / "claude" / "config" / "CLAUDE.md")
        assert link.read_text(encoding="utf-8") == (
            f"user={_TODAYS['USERNAME']} mail={_TODAYS['EMAIL']}\n"
        )

    def test_a_missing_file_is_set_up_as_a_first_install_sets_it_up(
        self, fake_home, plugin_root, monkeypatch
    ):
        _seed_template(plugin_root)
        monkeypatch.setattr(update._render_mod, "derive_defaults", lambda: dict(_TODAYS))

        update._update_instructions(fake_home, plugin_root)

        assert (fake_home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8") == (
            f"user={_TODAYS['USERNAME']} mail={_TODAYS['EMAIL']}\n"
        )

    def test_a_state_the_dispatch_does_not_know_is_a_bug_not_a_silent_skip(
        self, fake_home, plugin_root, monkeypatch
    ):
        monkeypatch.setattr(update, "classify_instructions", lambda *_: object())

        with pytest.raises(AssertionError, match="unhandled case"):
            update._update_instructions(fake_home, plugin_root)

    def test_the_dangling_link_setup_leaves_a_clones_live_links_its_own(
        self, fake_home, plugin_root, tmp_path
    ):
        _seed_template(plugin_root)
        _seed_script(plugin_root / "scripts", "praxion-dashboard")
        clone = tmp_path / "clone"
        clone_script = _seed_script(clone / "scripts", "praxion-dashboard")
        (fake_home / ".local" / "bin" / "praxion-dashboard").symlink_to(clone_script)
        clone_rule = clone / "rules" / "swe" / "coding-style.md"
        clone_rule.parent.mkdir(parents=True)
        clone_rule.write_text("# the clone's rule\n", encoding="utf-8")
        rule_link = _plant_link(fake_home, "swe/coding-style.md", clone_rule)
        _dangling_cache_link(fake_home)

        update._run_update_path(fake_home, plugin_root)

        bin_link = fake_home / ".local" / "bin" / "praxion-dashboard"
        assert (os.readlink(bin_link), os.readlink(rule_link)) == (
            str(clone_script),
            str(clone_rule),
        )

    def test_a_failed_setup_is_reported_once_and_the_marker_is_still_written(
        self, fake_home, plugin_root, marker_path
    ):
        _dangling_cache_link(fake_home)  # no template is seeded: the render fails

        lines = update._run_update_path(fake_home, plugin_root)

        assert lines == [
            "[Praxion] Update refresh could not finish (FileNotFoundError); "
            "run /praxion-complete-install to complete it."
        ]
        assert marker_path.exists()


class TestInstructionSetupPrompt:
    """The setup of a dangling link keeps the first install's confirmation prompt."""

    @pytest.fixture
    def dangling(self, fake_home, plugin_root, marker_path):
        _seed_template(plugin_root)
        _dangling_cache_link(fake_home)
        marker_path.write_text("")
        os.utime(marker_path, (1_000_000, 1_000_000))
        return fake_home

    def test_a_refusal_writes_the_decline_marker_and_no_completion_marker(
        self, dangling, plugin_root, marker_path, monkeypatch
    ):
        monkeypatch.setattr(sys, "stdin", io.StringIO("n\n"))

        update._run_update_path(dangling, plugin_root)

        assert (dangling / ".claude" / ".praxion-install-declined").exists()
        assert marker_path.stat().st_mtime == 1_000_000

    def test_a_refusal_is_no_failure_and_the_rules_and_scripts_are_still_refreshed(
        self, dangling, plugin_root, monkeypatch
    ):
        _seed_script(plugin_root / "scripts", "praxion-dashboard")
        monkeypatch.setattr(sys, "stdin", io.StringIO("n\n"))

        lines = update._run_update_path(dangling, plugin_root)

        assert lines == []
        assert (dangling / ".local" / "bin" / "praxion-dashboard").is_symlink()

    def test_the_prompt_shows_on_the_terminal_and_nowhere_else(
        self, dangling, plugin_root, marker_path, monkeypatch, capsys
    ):
        monkeypatch.setattr(sys, "stdin", io.StringIO("\n"))
        monkeypatch.setattr(update._render_mod, "derive_defaults", lambda: dict(_TODAYS))

        lines = update._run_update_path(dangling, plugin_root)

        captured = capsys.readouterr()
        assert _TODAYS["EMAIL"] in captured.err
        assert lines == ["[Praxion] Auto-install complete."]
        assert captured.out == ""
        assert marker_path.stat().st_mtime > 1_000_000
