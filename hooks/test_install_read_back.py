"""Behavioral tests for reading a linked render back, and the writer that never replaces it.

`read_back` answers what the render the link names carried, against the installed
version's template; `write_instructions` writes the slot the link does not resolve to.
Every home is a `tmp_path` one and every identity is made up. The fixtures and helpers
are the hook's own test module's, as in the other install suites.
"""

# ruff: noqa: F401, F811 (a fixture imported by name is found by its parameter name, which redefines it)
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from test_auto_complete_install import (
    _CARRIED,
    _NEW_TEMPLATE,
    _PREVIOUS_TEMPLATE,
    _TODAYS,
    _cached_version,
    _fill,
    _link_instructions,
    _no_ambient_plugin_root,
    _previous_render,
    _seed_template,
    fake_home,
    plugin_cache_dir,
    plugin_root,
    update,
)

_EDITED_BY_HAND = "# edited by hand, not a render of any template\n"
_NOT_AS_ROOT = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores the permissions this breaks"
)


@pytest.fixture(autouse=True)
def _never_derives(monkeypatch):
    """No test here may reach today's git identity: every value is given."""

    def refuse() -> dict[str, str]:
        raise AssertionError("derive_defaults was called")

    monkeypatch.setattr(update._render_mod, "derive_defaults", refuse)


def _state_naming(render: Path) -> update.CachedRender:
    """The state of a link naming `render`, a file under `<version>/claude/config/`."""
    return update.CachedRender(str(render.parents[2]), str(render))


@pytest.fixture
def previous(fake_home):
    """The previous version's render, filled with the made-up values."""
    return _previous_render(fake_home)


@pytest.fixture
def installed(plugin_root):
    """The installed version's root, its template ready."""
    _seed_template(plugin_root, _NEW_TEMPLATE)
    return plugin_root


class TestReadBack:
    def test_a_render_that_reads_back_gives_its_values_and_no_missing_key(
        self, previous, installed
    ):
        readback = update.read_back(_state_naming(previous), installed)

        assert readback == update.Carried(_CARRIED, frozenset())

    def test_a_key_only_the_installed_template_has_is_missing(self, previous, installed):
        _seed_template(installed, _NEW_TEMPLATE + "shell: {{SHELL_NAME}}\n")

        readback = update.read_back(_state_naming(previous), installed)

        assert readback == update.Carried(_CARRIED, frozenset({"SHELL_NAME"}))

    def test_a_key_left_as_its_placeholder_is_missing(self, previous, installed):
        left = {**_CARRIED, "GITHUB_URL": "{{GITHUB_URL}}"}
        previous.write_text(_fill(_PREVIOUS_TEMPLATE, left), encoding="utf-8")

        readback = update.read_back(_state_naming(previous), installed)

        assert readback == update.Carried(left, frozenset({"GITHUB_URL"}))

    def test_the_values_are_read_against_the_template_of_the_version_that_rendered_them(
        self, previous, installed
    ):
        _seed_template(installed, "# a different shape\nuser: {{USERNAME}}\n")

        readback = update.read_back(_state_naming(previous), installed)

        assert readback == update.Carried(_CARRIED, frozenset())

    def test_the_render_the_link_names_is_read_and_not_the_versions_primary(
        self, previous, installed
    ):
        alternate = previous.with_name("CLAUDE.alternate.md")
        alternate.write_text(_fill(_PREVIOUS_TEMPLATE, _TODAYS), encoding="utf-8")

        readback = update.read_back(_state_naming(alternate), installed)

        assert readback == update.Carried(_TODAYS, frozenset())

    @pytest.mark.parametrize(
        "damage",
        [
            pytest.param(lambda text: text + "a line added by hand\n", id="hand-edited"),
            pytest.param(lambda text: text[: len(text) // 2], id="cut-short"),
            pytest.param(lambda text: _EDITED_BY_HAND, id="another-template"),
            pytest.param(lambda text: text.replace("user:", "name:"), id="a-fixed-line-changed"),
        ],
    )
    def test_a_render_that_is_not_its_template_filled_in_is_unreadable(
        self, previous, installed, damage
    ):
        previous.write_text(damage(previous.read_text(encoding="utf-8")), encoding="utf-8")

        assert update.read_back(_state_naming(previous), installed) == update.Unreadable()

    def test_a_render_that_cannot_be_decoded_is_unreadable(self, previous, installed):
        previous.write_bytes(previous.read_bytes() + b"\xff\xfe")

        assert update.read_back(_state_naming(previous), installed) == update.Unreadable()

    def test_a_render_that_is_a_directory_raises_and_is_not_read_as_unreadable(
        self, previous, installed
    ):
        with pytest.raises(IsADirectoryError):
            update.read_back(
                update.CachedRender(str(previous.parents[2]), str(previous.parent)), installed
            )

    @_NOT_AS_ROOT
    def test_a_render_that_cannot_be_opened_raises_its_error(self, previous, installed):
        previous.chmod(0o000)
        try:
            with pytest.raises(PermissionError):
                update.read_back(_state_naming(previous), installed)
        finally:
            previous.chmod(0o644)

    def test_a_missing_template_of_the_rendering_version_raises(self, previous, installed):
        (previous.parent / "CLAUDE.md.tmpl").unlink()

        with pytest.raises(FileNotFoundError):
            update.read_back(_state_naming(previous), installed)

    def test_a_missing_installed_template_raises(self, previous, installed):
        (installed / "claude" / "config" / "CLAUDE.md.tmpl").unlink()

        with pytest.raises(FileNotFoundError):
            update.read_back(_state_naming(previous), installed)

    def test_nothing_is_printed_and_nothing_is_written(self, previous, installed, capsys, tmp_path):
        before = sorted(p for p in tmp_path.rglob("*"))

        update.read_back(_state_naming(previous), installed)

        output = capsys.readouterr()
        assert (output.out, output.err) == ("", "")
        assert sorted(p for p in tmp_path.rglob("*")) == before


def _file_state(path: Path) -> tuple[bytes, int]:
    return path.read_bytes(), path.stat().st_ino


def _files_holding_any(root: Path, values) -> list[Path]:
    """The regular files under `root` whose text holds any of `values`."""
    texts = {p: p.read_text(errors="replace") for p in root.rglob("*") if p.is_file()}
    return [p for p, text in texts.items() if not p.is_symlink() and any(v in text for v in values)]


class TestWriteInstructionsSlot:
    @pytest.fixture
    def primary(self, fake_home, installed):
        """The installed version's own primary render, edited by hand, and the link to it."""
        render = installed / "claude" / "config" / "CLAUDE.md"
        render.write_text(_EDITED_BY_HAND, encoding="utf-8")
        _link_instructions(fake_home, render)
        return render

    def test_a_link_into_the_roots_primary_gets_the_alternate_and_the_primary_is_untouched(
        self, primary, fake_home, installed
    ):
        before = _file_state(primary)

        update.write_instructions(fake_home, installed, _CARRIED)

        alternate = installed / "claude" / "config" / "CLAUDE.alternate.md"
        link = fake_home / ".claude" / "CLAUDE.md"
        assert _file_state(primary) == before
        assert os.readlink(link) == str(alternate)
        assert alternate.read_text(encoding="utf-8") == _fill(_NEW_TEMPLATE, _CARRIED)

    def test_a_root_spelled_with_a_parent_segment_is_still_the_root_the_link_resolves_into(
        self, primary, fake_home, installed
    ):
        before = _file_state(primary)

        update.write_instructions(fake_home, installed / "claude" / "..", _CARRIED)

        assert _file_state(primary) == before
        link = fake_home / ".claude" / "CLAUDE.md"
        assert link.read_text(encoding="utf-8") == _fill(_NEW_TEMPLATE, _CARRIED)

    def test_a_relative_link_into_the_roots_primary_gets_the_alternate(
        self, primary, fake_home, installed
    ):
        link = fake_home / ".claude" / "CLAUDE.md"
        link.unlink()
        link.symlink_to(os.path.relpath(primary, link.parent))
        before = _file_state(primary)

        update.write_instructions(fake_home, installed, _CARRIED)

        assert _file_state(primary) == before
        assert link.read_text(encoding="utf-8") == _fill(_NEW_TEMPLATE, _CARRIED)

    def test_a_link_spelled_through_a_symlinked_home_still_resolves_to_the_roots_primary(
        self, primary, fake_home, installed, tmp_path
    ):
        alias = tmp_path / "alias"
        alias.symlink_to(fake_home)
        link = fake_home / ".claude" / "CLAUDE.md"
        link.unlink()
        link.symlink_to(alias / primary.relative_to(fake_home))
        before = _file_state(primary)

        update.write_instructions(fake_home, installed, _CARRIED)

        alternate = installed / "claude" / "config" / "CLAUDE.alternate.md"
        assert _file_state(primary) == before
        assert alternate.read_text(encoding="utf-8") == _fill(_NEW_TEMPLATE, _CARRIED)

    def test_a_link_into_the_roots_alternate_gets_the_primary(self, primary, fake_home, installed):
        update.write_instructions(fake_home, installed, _CARRIED)
        alternate = installed / "claude" / "config" / "CLAUDE.alternate.md"
        before = _file_state(alternate)

        update.write_instructions(fake_home, installed, _TODAYS)

        link = fake_home / ".claude" / "CLAUDE.md"
        assert _file_state(alternate) == before
        assert os.readlink(link) == str(primary)
        assert primary.read_text(encoding="utf-8") == _fill(_NEW_TEMPLATE, _TODAYS)

    def test_a_link_into_another_version_gets_the_primary(self, previous, fake_home, installed):
        link = _link_instructions(fake_home, previous)

        update.write_instructions(fake_home, installed, _CARRIED)

        primary = installed / "claude" / "config" / "CLAUDE.md"
        assert os.readlink(link) == str(primary)
        assert not (installed / "claude" / "config" / "CLAUDE.alternate.md").exists()
        assert previous.read_text(encoding="utf-8") == _fill(_PREVIOUS_TEMPLATE, _CARRIED)

    def test_no_link_gets_the_primary(self, fake_home, installed):
        update.write_instructions(fake_home, installed, _CARRIED)

        primary = installed / "claude" / "config" / "CLAUDE.md"
        assert os.readlink(fake_home / ".claude" / "CLAUDE.md") == str(primary)

    def test_a_failing_rename_leaves_the_link_and_the_file_it_resolves_to_as_they_were(
        self, primary, fake_home, installed
    ):
        before = _file_state(primary)
        link = fake_home / ".claude" / "CLAUDE.md"
        alternate = installed / "claude" / "config" / "CLAUDE.alternate.md"
        alternate.mkdir()  # a rename of a file over a directory fails, with no stub

        with pytest.raises(IsADirectoryError):
            update.write_instructions(fake_home, installed, _CARRIED)

        assert (os.readlink(link), _file_state(primary)) == (str(primary), before)
        assert sorted(p.name for p in primary.parent.iterdir()) == [
            "CLAUDE.alternate.md",
            "CLAUDE.md",
            "CLAUDE.md.tmpl",
        ]

    def test_a_failing_rename_into_the_primary_leaves_the_previous_render_linked(
        self, previous, fake_home, installed
    ):
        link = _link_instructions(fake_home, previous)
        (installed / "claude" / "config" / "CLAUDE.md").mkdir()

        with pytest.raises(IsADirectoryError):
            update.write_instructions(fake_home, installed, _CARRIED)

        assert os.readlink(link) == str(previous)
        assert previous.read_text(encoding="utf-8") == _fill(_PREVIOUS_TEMPLATE, _CARRIED)

    def test_nothing_is_printed_and_no_other_copy_is_saved(
        self, primary, fake_home, installed, capsys, tmp_path
    ):
        update.write_instructions(fake_home, installed, _CARRIED)

        output = capsys.readouterr()
        assert (output.out, output.err) == ("", "")
        holders = _files_holding_any(tmp_path, _CARRIED.values())
        assert holders == [installed / "claude" / "config" / "CLAUDE.alternate.md"]


class TestConsecutiveUpdatesAfterAnAlternateWrite:
    @pytest.fixture
    def alternate_linked(self, fake_home, installed):
        """The link after a hand write into the installed version's alternate render.

        The stale primary carries one identity and the alternate another, so a reader
        that still assumed the primary recovers the wrong one.
        """
        primary = installed / "claude" / "config" / "CLAUDE.md"
        primary.write_text(_fill(_NEW_TEMPLATE, _CARRIED), encoding="utf-8")
        link = _link_instructions(fake_home, primary)
        update.write_instructions(fake_home, installed, _TODAYS)
        return link

    def _updated_to(self, home: Path, version: str) -> Path:
        root = _cached_version(home, version)
        _seed_template(root, _NEW_TEMPLATE)
        update._update_instructions(home, root)
        return root / "claude" / "config" / "CLAUDE.md"

    def test_the_next_update_reads_the_alternate_and_links_its_own_primary(
        self, alternate_linked, fake_home
    ):
        primary = self._updated_to(fake_home, "10.0.0")

        assert os.readlink(alternate_linked) == str(primary)
        assert primary.read_text(encoding="utf-8") == _fill(_NEW_TEMPLATE, _TODAYS)

    def test_the_update_after_that_reads_the_new_primary(self, alternate_linked, fake_home):
        self._updated_to(fake_home, "10.0.0")

        primary = self._updated_to(fake_home, "10.0.1")

        assert os.readlink(alternate_linked) == str(primary)
        assert primary.read_text(encoding="utf-8") == _fill(_NEW_TEMPLATE, _TODAYS)
