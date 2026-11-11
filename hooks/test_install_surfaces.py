"""Behavioral tests for the install steps and the run's decision tree.

Each step in process against a throwaway HOME -- surface detection, rendering the
instructions, resolving the plugin root, linking rules and scripts -- then the sequence of
them and `_run`, which decides which guard wins. The fixtures and helpers are the hook's
own test module's (`test_auto_complete_install`); this module imports them so every suite
lays out one plugin and one HOME the same way.
"""

# ruff: noqa: F401, F811 (a fixture imported by name is found by its parameter name, which redefines it)
from __future__ import annotations

import io
import os
import shutil
import sys

import pytest
from test_auto_complete_install import (
    _VALUES,
    _cached_version,
    _fake_home_module,
    _link_instructions,
    _no_ambient_plugin_root,
    _plant_link,
    _previous_render,
    _render_module_reachable_by_the_hook_subprocess,
    _rule_links,
    _seed_script,
    _seed_template,
    claude_md_symlink,
    fake_home,
    marker_path,
    plugin_cache_dir,
    plugin_root,
    rules_sentinel,
    update,
)


class TestSurfacePresence:
    def test_symlinked_claude_md_plus_rules_sentinel_counts_as_installed(
        self, fake_home, claude_md_symlink, rules_sentinel, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)

        assert module._surfaces_installed(fake_home) is True

    def test_a_regular_claude_md_is_not_an_installed_surface(
        self, fake_home, rules_sentinel, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        # A hand-authored ~/.claude/CLAUDE.md is a real file, not a plugin
        # symlink. Treating it as installed would leave the operator's own
        # file permanently mistaken for a rendered one.
        (fake_home / ".claude" / "CLAUDE.md").write_text("# my own notes\n")

        assert module._surfaces_installed(fake_home) is False

    def test_missing_rules_sentinel_is_not_an_installed_surface(
        self, fake_home, claude_md_symlink, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)

        assert module._surfaces_installed(fake_home) is False

    def test_a_dangling_claude_md_link_is_not_an_installed_surface(
        self, fake_home, rules_sentinel, tmp_path, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        # The rendered file lived in an old plugin version's directory, which
        # Claude Code has since removed.
        (fake_home / ".claude" / "CLAUDE.md").symlink_to(tmp_path / "removed" / "CLAUDE.md")

        assert module._surfaces_installed(fake_home) is False

    def test_a_live_link_into_the_cache_is_an_installed_surface(
        self, fake_home, rules_sentinel, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        _link_instructions(fake_home, _previous_render(fake_home))

        assert module._surfaces_installed(fake_home) is True

    def test_a_dangling_link_into_the_cache_is_not_an_installed_surface(
        self, fake_home, rules_sentinel, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        removed = _cached_version(fake_home, "9.9.8") / "claude" / "config" / "CLAUDE.md"
        _link_instructions(fake_home, removed)

        assert module._surfaces_installed(fake_home) is False


class TestClaudeMdRendering:
    def test_renders_the_template_and_links_it_into_the_claude_directory(
        self, fake_home, plugin_root, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        _seed_template(plugin_root)

        module._render_claude_md(fake_home, _VALUES, plugin_root)

        link = fake_home / ".claude" / "CLAUDE.md"
        assert link.is_symlink(), "CLAUDE.md must be a symlink so plugin updates propagate"
        assert link.read_text(encoding="utf-8") == "user=@someone mail=someone@example.com\n"

    def test_replaces_a_previously_rendered_symlink(
        self, fake_home, plugin_root, tmp_path, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        _seed_template(plugin_root)
        stale_target = tmp_path / "stale.md"
        stale_target.write_text("stale\n", encoding="utf-8")
        (fake_home / ".claude" / "CLAUDE.md").symlink_to(stale_target)

        module._render_claude_md(fake_home, _VALUES, plugin_root)

        assert (fake_home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8").startswith("user=")

    def test_replaces_a_regular_file_left_at_the_link_path(
        self, fake_home, plugin_root, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        _seed_template(plugin_root)
        (fake_home / ".claude" / "CLAUDE.md").write_text("hand written\n", encoding="utf-8")

        module._render_claude_md(fake_home, _VALUES, plugin_root)

        assert (fake_home / ".claude" / "CLAUDE.md").is_symlink()

    def test_a_missing_template_surfaces_rather_than_silently_producing_nothing(
        self, fake_home, plugin_root, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)

        # `_render_claude_md` documents that it raises; `_perform_install` is
        # the layer that decides to swallow. Losing the raise here would make
        # a broken plugin cache indistinguishable from a good one.
        with pytest.raises(FileNotFoundError):
            module._render_claude_md(fake_home, _VALUES, plugin_root)


class TestPluginRoot:
    """The hook installs from the plugin's own version directory."""

    def test_the_registered_install_path_is_the_plugin_root(
        self, fake_home, plugin_root, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)

        assert module._plugin_root(fake_home) == plugin_root

    def test_the_hooks_own_plugin_root_wins_over_the_registry(
        self, fake_home, tmp_path, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        own = tmp_path / "checkout"
        own.mkdir()
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(own))

        assert module._plugin_root(fake_home) == own

    def test_the_unversioned_cache_parent_alone_is_no_plugin(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        (home / ".claude" / "plugins" / "cache" / "bit-agora" / "praxion").mkdir(parents=True)
        module = _fake_home_module(monkeypatch, home)

        # Claude Code never installs a plugin's files into the cache parent.
        assert module._plugin_root(home) is None

    def test_a_registry_naming_a_missing_directory_is_no_plugin(
        self, fake_home, plugin_root, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        shutil.rmtree(plugin_root)

        assert module._plugin_root(fake_home) is None


class TestRuleLinking:
    """A cold install links through the installer's own library."""

    def test_links_exactly_the_manifests_symlink_rules(self, fake_home, plugin_root, monkeypatch):
        module = _fake_home_module(monkeypatch, fake_home)

        module._link_rules(fake_home, plugin_root)

        # Not the hook-delivered resident, the catalog, the directory guide or
        # reference material: only what the manifest marks `install: symlink`.
        assert sorted(_rule_links(fake_home)) == [
            "swe/agent-behavioral-contract.md",
            "swe/coding-style.md",
        ]

    def test_a_rule_that_became_hook_delivered_has_its_stale_link_removed(
        self, fake_home, plugin_root, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        rel = "swe/agent-model-routing-resident.md"
        stale = _plant_link(fake_home, rel, plugin_root / "rules" / rel)

        module._link_rules(fake_home, plugin_root)

        assert not stale.is_symlink(), "a re-install must clean up the previous install's link"

    def test_relinking_replaces_an_existing_symlink(
        self, fake_home, plugin_root, tmp_path, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        outdated = tmp_path / "outdated.md"
        outdated.write_text("outdated\n", encoding="utf-8")
        _plant_link(fake_home, "swe/coding-style.md", outdated)

        module._link_rules(fake_home, plugin_root)

        assert (
            _rule_links(fake_home)["swe/coding-style.md"]
            == (plugin_root / "rules" / "swe" / "coding-style.md").resolve()
        )

    def test_a_plugin_without_a_rules_directory_links_nothing(
        self, fake_home, plugin_root, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        shutil.rmtree(plugin_root / "rules")

        module._link_rules(fake_home, plugin_root)

        assert _rule_links(fake_home) == {}


class TestRuleRefresh:
    """After an update the hook refreshes the rule links without taking any over."""

    def test_sweeps_an_older_versions_link_to_a_now_hook_delivered_rule(
        self, fake_home, plugin_root, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        rel = "swe/agent-model-routing-resident.md"
        older = plugin_root.parent / "9.9.8" / "rules" / rel
        older.parent.mkdir(parents=True)
        older.write_text("# routing resident, as an older version linked it\n", encoding="utf-8")
        stale = _plant_link(fake_home, rel, older)

        module._refresh_rules(fake_home, plugin_root)

        # Left in place, every session would keep loading a rule the plugin
        # now delivers only where the project is managed.
        assert not stale.is_symlink()

    def test_links_a_manifest_rule_that_has_no_link(self, fake_home, plugin_root, monkeypatch):
        module = _fake_home_module(monkeypatch, fake_home)

        module._refresh_rules(fake_home, plugin_root)

        assert (
            _rule_links(fake_home)["swe/coding-style.md"]
            == (plugin_root / "rules" / "swe" / "coding-style.md").resolve()
        )

    def test_relinks_a_dangling_link(self, fake_home, plugin_root, tmp_path, monkeypatch):
        module = _fake_home_module(monkeypatch, fake_home)
        _plant_link(fake_home, "swe/coding-style.md", tmp_path / "removed-version" / "gone.md")

        module._refresh_rules(fake_home, plugin_root)

        assert (
            _rule_links(fake_home)["swe/coding-style.md"]
            == (plugin_root / "rules" / "swe" / "coding-style.md").resolve()
        )

    def test_leaves_a_live_link_into_a_checkout_as_it_is(
        self, fake_home, plugin_root, tmp_path, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        checkout_rule = tmp_path / "checkout" / "rules" / "swe" / "coding-style.md"
        checkout_rule.parent.mkdir(parents=True)
        checkout_rule.write_text("# coding style, from a clone install\n", encoding="utf-8")
        _plant_link(fake_home, "swe/coding-style.md", checkout_rule)

        module._refresh_rules(fake_home, plugin_root)

        # A clone install owns its links; re-pointing them at the plugin cache
        # would silently move a developer off their checkout.
        assert _rule_links(fake_home)["swe/coding-style.md"] == checkout_rule.resolve()

    def test_never_replaces_a_regular_file_at_a_rule_path(
        self, fake_home, plugin_root, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        own = fake_home / ".claude" / "rules" / "swe" / "coding-style.md"
        own.write_text("# the operator's own rule\n", encoding="utf-8")

        module._refresh_rules(fake_home, plugin_root)

        assert not own.is_symlink()
        assert own.read_text(encoding="utf-8") == "# the operator's own rule\n"


class TestScriptLinking:
    def test_absent_scripts_directory_is_a_no_op(self, fake_home, plugin_root, monkeypatch):
        module = _fake_home_module(monkeypatch, fake_home)

        module._link_scripts(fake_home, plugin_root)

        assert list((fake_home / ".local" / "bin").iterdir()) == []

    def test_links_executable_scripts_onto_the_path(self, fake_home, plugin_root, monkeypatch):
        module = _fake_home_module(monkeypatch, fake_home)
        _seed_script(plugin_root / "scripts", "praxion-dashboard")

        module._link_scripts(fake_home, plugin_root)

        assert (fake_home / ".local" / "bin" / "praxion-dashboard").is_symlink()

    @pytest.mark.parametrize(
        ("name", "executable", "reason"),
        [
            ("helper.py", False, "not executable -- not a user-facing entry point"),
            ("merge_driver_observations.py", True, "git invokes merge drivers, not the operator"),
            ("post-merge-hook.sh", True, "git invokes hooks, not the operator"),
        ],
    )
    def test_non_operator_facing_files_stay_off_the_path(
        self, fake_home, plugin_root, monkeypatch, name, executable, reason
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        _seed_script(plugin_root / "scripts", name, executable=executable)

        module._link_scripts(fake_home, plugin_root)

        assert not (fake_home / ".local" / "bin" / name).exists(), reason

    def test_relinking_replaces_an_existing_symlink(
        self, fake_home, plugin_root, tmp_path, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        script = _seed_script(plugin_root / "scripts", "praxion-dashboard")
        outdated = tmp_path / "outdated-dashboard"
        outdated.write_text("#!/bin/sh\n", encoding="utf-8")
        dest = fake_home / ".local" / "bin" / "praxion-dashboard"
        dest.symlink_to(outdated)

        module._link_scripts(fake_home, plugin_root)

        assert dest.resolve() == script.resolve()


class TestFullInstallSequence:
    def test_runs_every_install_step(self, fake_home, plugin_root, monkeypatch):
        module = _fake_home_module(monkeypatch, fake_home)
        _seed_template(plugin_root)
        _seed_script(plugin_root / "scripts", "praxion-dashboard")

        module._run_install(fake_home, _VALUES, plugin_root)

        assert (fake_home / ".claude" / "CLAUDE.md").is_symlink()
        assert (fake_home / ".claude" / "rules" / "swe" / "coding-style.md").is_symlink()
        assert (fake_home / ".local" / "bin" / "praxion-dashboard").is_symlink()


class TestPerformInstall:
    def test_auto_complete_installs_and_records_completion(
        self, fake_home, plugin_root, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        _seed_template(plugin_root)

        module._perform_install(fake_home, _VALUES, auto_complete=True, root=plugin_root)

        assert (fake_home / ".claude" / "CLAUDE.md").is_symlink()
        assert (fake_home / ".claude" / ".praxion-complete-installed").exists()

    def test_a_refusal_records_the_decline_and_installs_nothing(
        self, fake_home, plugin_root, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        _seed_template(plugin_root)
        monkeypatch.setattr(sys, "stdin", io.StringIO("n\n"))

        module._perform_install(fake_home, _VALUES, auto_complete=False, root=plugin_root)

        assert (fake_home / ".claude" / ".praxion-install-declined").exists()
        assert not (fake_home / ".claude" / ".praxion-complete-installed").exists()
        assert not (fake_home / ".claude" / "CLAUDE.md").exists()

    def test_a_failed_install_still_records_completion(
        self, fake_home, plugin_root, monkeypatch, capsys
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        # No template seeded: `_render_claude_md` raises FileNotFoundError.

        module._perform_install(fake_home, _VALUES, auto_complete=True, root=plugin_root)

        # Deliberate: without the marker the hook would retry the same failing
        # install on every single session start.
        assert (fake_home / ".claude" / ".praxion-complete-installed").exists()
        # ...but the failure is reported as one, with the command that completes
        # it: a success line here once hid an install that did nothing at all.
        reported = capsys.readouterr().err
        assert "Auto-install complete" not in reported
        assert "/praxion-complete-install" in reported

    def test_a_prompt_that_cannot_run_is_treated_as_consent(
        self, fake_home, plugin_root, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        _seed_template(plugin_root)

        def _explodes(_values: dict) -> bool:
            raise RuntimeError("terminal is gone")

        monkeypatch.setattr(update, "_prompt_with_timeout", _explodes)

        module._perform_install(fake_home, _VALUES, auto_complete=False, root=plugin_root)

        assert (fake_home / ".claude" / ".praxion-complete-installed").exists()


class TestRunFlow:
    """`_run` is the whole decision tree: which guard wins, and in what order."""

    def test_the_kill_switch_stops_everything(self, fake_home, plugin_root, monkeypatch):
        module = _fake_home_module(monkeypatch, fake_home)
        _seed_template(plugin_root)
        monkeypatch.setenv("PRAXION_DISABLE_AUTO_COMPLETE", "1")
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))

        module._run()

        assert not (fake_home / ".claude" / ".praxion-complete-installed").exists()
        assert not (fake_home / ".claude" / "CLAUDE.md").exists()

    def test_a_fresh_marker_short_circuits_the_install(
        self,
        fake_home,
        plugin_root,
        plugin_cache_dir,
        marker_path,
        monkeypatch,
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        _seed_template(plugin_root)
        marker_path.write_text("")
        os.utime(plugin_cache_dir, (1_000_000, 1_000_000))
        os.utime(marker_path, (2_000_000, 2_000_000))
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))

        module._run()

        assert not (fake_home / ".claude" / "CLAUDE.md").exists()

    def test_already_installed_surfaces_only_record_the_marker(
        self, fake_home, claude_md_symlink, rules_sentinel, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
        original = claude_md_symlink.resolve()

        module._run()

        assert (fake_home / ".claude" / ".praxion-complete-installed").exists()
        # A clone-install's surfaces must not be re-pointed at the plugin cache.
        assert claude_md_symlink.resolve() == original

    def test_already_installed_surfaces_get_their_missing_rule_links(
        self, fake_home, plugin_root, claude_md_symlink, rules_sentinel, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))

        module._run()

        # A rule a newer version links reaches an existing install on its next
        # session after the update, with no reinstall.
        assert (
            _rule_links(fake_home)["swe/coding-style.md"]
            == (plugin_root / "rules" / "swe" / "coding-style.md").resolve()
        )

    def test_no_resolvable_plugin_installs_nothing_and_records_nothing(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        (home / ".claude" / "plugins" / "cache" / "bit-agora" / "praxion").mkdir(parents=True)
        module = _fake_home_module(monkeypatch, home)
        monkeypatch.setenv("PRAXION_AUTO_COMPLETE", "1")
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))

        module._run()

        # With no marker, a later session that can resolve the plugin still
        # completes the install instead of trusting one that never ran.
        assert not (home / ".claude" / "CLAUDE.md").exists()
        assert not (home / ".claude" / ".praxion-complete-installed").exists()

    def test_a_cold_start_performs_the_install(self, fake_home, plugin_root, monkeypatch):
        module = _fake_home_module(monkeypatch, fake_home)
        _seed_template(plugin_root)
        monkeypatch.setenv("PRAXION_AUTO_COMPLETE", "1")
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))

        module._run()

        assert (fake_home / ".claude" / "CLAUDE.md").is_symlink()
        assert (fake_home / ".claude" / ".praxion-complete-installed").exists()

    def test_undiscoverable_git_identity_falls_back_to_anonymous_defaults(
        self, fake_home, plugin_root, monkeypatch
    ):
        module = _fake_home_module(monkeypatch, fake_home)
        _seed_template(plugin_root)
        monkeypatch.setenv("PRAXION_AUTO_COMPLETE", "1")
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))

        def _no_identity() -> dict:
            raise OSError("git not on PATH")

        monkeypatch.setattr(update._render_mod, "derive_defaults", _no_identity)

        module._run()

        rendered = (fake_home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
        assert "@anon" in rendered
        assert "anon@unknown" in rendered
