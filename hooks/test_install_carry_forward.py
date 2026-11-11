"""Behavioral tests for carrying the instructions' values across a plugin update.

A link into another cached version's render moves to this version's, with the values the
previous render carried and without a second derivation. The fixtures and helpers are the
hook's own test module's (`test_auto_complete_install`); this module imports them so every
suite lays out one plugin and one HOME the same way.
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
    _fake_home_module,
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


def _file_state(path: Path) -> tuple:
    status = path.stat()
    return path.read_bytes(), status.st_ino, status.st_mtime_ns


def _record_derivations(monkeypatch, values: dict[str, str]) -> list:
    calls: list = []

    def derive() -> dict[str, str]:
        calls.append("derived")
        return dict(values)

    monkeypatch.setattr(update._render_mod, "derive_defaults", derive)
    return calls


def _files_holding(root: Path, values, excluding: set[Path]) -> list[str]:
    """The regular files under `root`, other than `excluding`, that contain any of `values`."""
    regular = (p for p in root.rglob("*") if p.is_file() and not p.is_symlink())
    return [
        str(path.relative_to(root))
        for path in regular
        if path not in excluding and any(v in path.read_text(errors="replace") for v in values)
    ]


def _values_in(text: str, values) -> list[str]:
    return [value for value in values if value in text]


def _refuse_replacing(monkeypatch, destination: Path) -> None:
    """Make the rename over `destination`, and only that one, fail."""
    real_replace = os.replace

    def replace(source, target) -> None:
        if Path(target) == destination:
            raise OSError("refused")
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", replace)


_not_as_root = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores the permissions these break"
)


class TestInstructionsCarryForward:
    """A link into another cached version's render moves to this version's, values kept."""

    @pytest.fixture
    def todays_identity(self, tmp_path, monkeypatch):
        """Git now answers with another identity than the one the previous render carried."""
        gitconfig = tmp_path / "gitconfig"
        gitconfig.write_text(
            f"[user]\n\tname = Later Person\n\temail = {_TODAYS['EMAIL']}\n", encoding="utf-8"
        )
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
        monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")

    @pytest.fixture
    def updated(self, fake_home, plugin_root, monkeypatch):
        """The previous version's render is linked, and this version ships a new template."""
        module = _fake_home_module(monkeypatch, fake_home)
        previous = _previous_render(fake_home)
        link = _link_instructions(fake_home, previous)
        _seed_template(plugin_root, _NEW_TEMPLATE)
        return module, previous, link

    @pytest.mark.usefixtures("todays_identity")
    def test_the_new_template_is_filled_with_the_previous_renders_values(
        self, updated, fake_home, plugin_root
    ):
        module, _, link = updated

        update._update_instructions(fake_home, plugin_root)

        assert link.read_text(encoding="utf-8") == _fill(_NEW_TEMPLATE, _CARRIED)

    def test_the_link_points_at_this_versions_render(self, updated, fake_home, plugin_root):
        module, _, link = updated

        update._update_instructions(fake_home, plugin_root)

        assert os.readlink(link) == str(plugin_root / "claude" / "config" / "CLAUDE.md")

    def test_the_previous_render_is_left_as_it_was(self, updated, fake_home, plugin_root):
        module, previous, _ = updated
        before = _file_state(previous)

        update._update_instructions(fake_home, plugin_root)

        assert _file_state(previous) == before

    def test_a_relative_link_into_the_previous_version_is_carried_forward(
        self, fake_home, plugin_root, monkeypatch
    ):
        monkeypatch.setenv("HOME", str(fake_home))
        previous = _previous_render(fake_home)
        link = _link_instructions(fake_home, previous.relative_to(fake_home / ".claude"))
        _seed_template(plugin_root, _NEW_TEMPLATE)

        update._update_instructions(fake_home, plugin_root)

        assert link.read_text(encoding="utf-8") == _fill(_NEW_TEMPLATE, _CARRIED)

    def test_a_default_fills_only_the_key_the_previous_render_never_carried(
        self, fake_home, plugin_root, monkeypatch
    ):
        monkeypatch.setenv("HOME", str(fake_home))
        without_web = _PREVIOUS_TEMPLATE.replace("web: {{GITHUB_URL}}\n", "")
        link = _link_instructions(fake_home, _previous_render(fake_home, without_web))
        _seed_template(plugin_root, _NEW_TEMPLATE)
        _record_derivations(monkeypatch, _TODAYS)

        update._update_instructions(fake_home, plugin_root)

        expected = {**_CARRIED, "GITHUB_URL": _TODAYS["GITHUB_URL"]}
        assert link.read_text(encoding="utf-8") == _fill(_NEW_TEMPLATE, expected)

    def test_a_value_equal_to_its_own_placeholder_counts_as_missing(self):
        carried = {**_CARRIED, "GITHUB_URL": "{{GITHUB_URL}}"}

        assert update._missing_keys(_NEW_TEMPLATE, carried) == frozenset({"GITHUB_URL"})

    def test_a_default_fills_a_key_the_previous_render_left_as_its_placeholder(
        self, fake_home, plugin_root, monkeypatch
    ):
        monkeypatch.setenv("HOME", str(fake_home))
        previous = _previous_render(fake_home)
        unfilled = {**_CARRIED, "GITHUB_URL": "{{GITHUB_URL}}"}
        previous.write_text(_fill(_PREVIOUS_TEMPLATE, unfilled), encoding="utf-8")
        link = _link_instructions(fake_home, previous)
        _seed_template(plugin_root, _NEW_TEMPLATE)
        _record_derivations(monkeypatch, _TODAYS)

        update._update_instructions(fake_home, plugin_root)

        expected = {**_CARRIED, "GITHUB_URL": _TODAYS["GITHUB_URL"]}
        assert link.read_text(encoding="utf-8") == _fill(_NEW_TEMPLATE, expected)

    def test_no_default_is_derived_when_every_key_was_carried(
        self, updated, fake_home, plugin_root, monkeypatch
    ):
        module, _, _ = updated
        calls = _record_derivations(monkeypatch, _TODAYS)

        update._update_instructions(fake_home, plugin_root)

        assert calls == []

    def test_a_key_neither_carried_nor_derivable_stays_a_named_placeholder(
        self, updated, fake_home, plugin_root, monkeypatch, capsys
    ):
        module, _, link = updated
        _seed_template(plugin_root, _NEW_TEMPLATE + "shell: {{SHELL_NAME}}\n")
        _record_derivations(monkeypatch, _TODAYS)

        update._update_instructions(fake_home, plugin_root)

        assert link.read_text(encoding="utf-8").endswith("shell: {{SHELL_NAME}}\n")
        assert "{{SHELL_NAME}}" in capsys.readouterr().err

    def test_an_unrecoverable_render_raises_its_own_error_type(
        self, updated, fake_home, plugin_root
    ):
        module, previous, _ = updated
        previous.write_text(previous.read_text(encoding="utf-8") + "a line edited by hand\n")

        with pytest.raises(update.UnrecoverableRenderError):
            update._update_instructions(fake_home, plugin_root)

    def test_an_unrecoverable_render_keeps_the_previous_link_and_writes_no_render(
        self, updated, fake_home, plugin_root
    ):
        module, previous, link = updated
        previous.write_text(previous.read_text(encoding="utf-8") + "a line edited by hand\n")

        with pytest.raises(update.UnrecoverableRenderError):
            update._update_instructions(fake_home, plugin_root)

        assert os.readlink(link) == str(previous)
        assert sorted(p.name for p in (plugin_root / "claude" / "config").iterdir()) == [
            "CLAUDE.md.tmpl"
        ]

    def test_an_unrecoverable_render_is_reported_in_one_line_naming_its_type(
        self, updated, fake_home, plugin_root, monkeypatch
    ):
        module, previous, _ = updated
        previous.write_text("# rewritten by hand\n", encoding="utf-8")
        monkeypatch.setattr(update, "_UPDATE_STEPS", (update._update_instructions,))

        lines = update._run_update_path(fake_home, plugin_root)

        assert lines == [
            "[Praxion] Update refresh could not finish (UnrecoverableRenderError); "
            "run /praxion-complete-install to complete it."
        ]

    @_not_as_root
    def test_an_unreadable_new_template_keeps_the_previous_render(
        self, updated, fake_home, plugin_root
    ):
        module, previous, link = updated
        template = plugin_root / "claude" / "config" / "CLAUDE.md.tmpl"
        template.chmod(0o000)
        try:
            with pytest.raises(PermissionError):
                update._update_instructions(fake_home, plugin_root)
        finally:
            template.chmod(0o644)

        assert (os.readlink(link), link.read_text(encoding="utf-8")) == (
            str(previous),
            _fill(_PREVIOUS_TEMPLATE, _CARRIED),
        )

    @_not_as_root
    def test_an_unwritable_render_directory_keeps_the_previous_render_and_no_temporary(
        self, updated, fake_home, plugin_root
    ):
        module, previous, link = updated
        config = plugin_root / "claude" / "config"
        config.chmod(0o555)
        try:
            with pytest.raises(PermissionError):
                update._update_instructions(fake_home, plugin_root)
        finally:
            config.chmod(0o755)

        assert os.readlink(link) == str(previous)
        assert sorted(p.name for p in config.iterdir()) == ["CLAUDE.md.tmpl"]

    def test_a_failed_rename_of_the_render_keeps_the_previous_render_and_no_temporary(
        self, updated, fake_home, plugin_root, monkeypatch
    ):
        module, previous, link = updated
        config = plugin_root / "claude" / "config"
        _refuse_replacing(monkeypatch, config / "CLAUDE.md")

        with pytest.raises(OSError, match="refused"):
            update._update_instructions(fake_home, plugin_root)

        assert os.readlink(link) == str(previous)
        assert sorted(p.name for p in config.iterdir()) == ["CLAUDE.md.tmpl"]

    def test_a_failed_swap_of_the_link_keeps_the_previous_render_and_no_temporary(
        self, updated, fake_home, plugin_root, monkeypatch
    ):
        module, previous, link = updated
        before = sorted(p.name for p in link.parent.iterdir())
        _refuse_replacing(monkeypatch, link)

        with pytest.raises(OSError, match="refused"):
            update._update_instructions(fake_home, plugin_root)

        assert (os.readlink(link), link.read_text(encoding="utf-8")) == (
            str(previous),
            _fill(_PREVIOUS_TEMPLATE, _CARRIED),
        )
        assert sorted(p.name for p in link.parent.iterdir()) == before

    def test_a_link_already_into_this_version_is_left_as_it_is(
        self, fake_home, plugin_root, monkeypatch
    ):
        monkeypatch.setenv("HOME", str(fake_home))
        _seed_template(plugin_root, _NEW_TEMPLATE)
        render = plugin_root / "claude" / "config" / "CLAUDE.md"
        render.write_text(_fill(_NEW_TEMPLATE, _CARRIED), encoding="utf-8")
        link = _link_instructions(fake_home, render)
        before = (os.readlink(link), _file_state(render))

        update._update_instructions(fake_home, plugin_root)

        assert (os.readlink(link), _file_state(render)) == before

    def test_a_clone_link_and_its_render_are_left_as_they_are(
        self, fake_home, plugin_root, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("HOME", str(fake_home))
        _seed_template(plugin_root, _NEW_TEMPLATE)
        clone_render = tmp_path / "dev" / "praxion" / "claude" / "config" / "CLAUDE.md"
        clone_render.parent.mkdir(parents=True)
        clone_render.write_text("# a developer's own render\n", encoding="utf-8")
        link = _link_instructions(fake_home, clone_render)
        before = (os.readlink(link), _file_state(clone_render))

        update._update_instructions(fake_home, plugin_root)

        assert (os.readlink(link), _file_state(clone_render)) == before
        assert not (plugin_root / "claude" / "config" / "CLAUDE.md").exists()

    def test_nothing_is_read_from_stdin(self, updated, fake_home, plugin_root, monkeypatch):
        module, _, link = updated

        class _NoAnswers:
            def read(self, *_args) -> str:
                raise AssertionError("the update path read stdin")

            readline = read

        monkeypatch.setattr(sys, "stdin", _NoAnswers())

        update._update_instructions(fake_home, plugin_root)

        assert link.read_text(encoding="utf-8") == _fill(_NEW_TEMPLATE, _CARRIED)

    def test_no_personal_value_is_printed(
        self, updated, fake_home, plugin_root, monkeypatch, capsys
    ):
        module, _, _ = updated
        _seed_template(plugin_root, _NEW_TEMPLATE + "shell: {{SHELL_NAME}}\n")
        _record_derivations(monkeypatch, _TODAYS)

        update._update_instructions(fake_home, plugin_root)

        output = "".join(capsys.readouterr())
        assert _values_in(output, (*_CARRIED.values(), *_TODAYS.values())) == []

    def test_no_personal_value_is_written_outside_the_two_renders(
        self, updated, fake_home, plugin_root, tmp_path
    ):
        module, previous, _ = updated

        update._update_instructions(fake_home, plugin_root)

        renders = {previous, plugin_root / "claude" / "config" / "CLAUDE.md"}
        assert _files_holding(tmp_path, _CARRIED.values(), excluding=renders) == []
