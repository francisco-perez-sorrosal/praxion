"""The installer's health check judges rule links against the manifest.

`install.sh --check` once counted the `*.md` symlinks under `~/.claude/rules/`
and passed on any count above zero. A link to a rule the manifest had moved to
`install: hook-deliver` therefore passed as healthy, although the next install
sweeps it and, until then, every session loads that rule natively. The check
now applies the sweep's own predicate: each stale link (one the sweep would
remove) and each missing link (a manifest `install: symlink` rule with no
working link) is named, and either one fails the check.

Tested end to end through `install_claude.sh code --check`, which is read-only,
against a temp HOME whose rules directory the installer's own `link_rules`
builds, with `claude`/`npm` stubbed first on PATH. The rules each case plants
are read from the manifest through the installer's reader, never named here,
so a rule changing its install type cannot leave a case testing nothing.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL_CLAUDE = REPO_ROOT / "install_claude.sh"
INSTALL_SHARED = REPO_ROOT / "lib" / "install_shared.sh"
RULES_SOURCE = REPO_ROOT / "rules"


def _shared(command: str, home: Path) -> str:
    """Run `command` in bash with the installer's shared library sourced."""
    result = subprocess.run(
        ["bash", "-c", f'source "{INSTALL_SHARED}"; {command}'],
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(home)},
        check=True,
        timeout=60,
    )
    return result.stdout


def _manifest_rules(install_type: str, home: Path) -> list[str]:
    output = _shared(f'manifest_rule_paths "{RULES_SOURCE}/_manifest.yaml" {install_type}', home)
    return output.split()


def _stub_bin(tmp_path: Path) -> Path:
    bindir = tmp_path / "stubbin"
    bindir.mkdir()
    for name in ("claude", "npm"):
        stub = bindir / name
        stub.write_text("#!/bin/sh\nexit 1\n")
        stub.chmod(0o755)
    return bindir


def _check(home: Path, tmp_path: Path) -> str:
    env = {
        **os.environ,
        "HOME": str(home),
        "PATH": f"{_stub_bin(tmp_path)}{os.pathsep}{os.environ['PATH']}",
        "NO_COLOR": "1",
    }
    result = subprocess.run(
        ["bash", str(INSTALL_CLAUDE), "code", "--check"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
    )
    return result.stdout + result.stderr


@pytest.fixture
def home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    _shared(f'link_rules "{RULES_SOURCE}" "$HOME/.claude/rules"', home)
    return home


@pytest.fixture
def rules_dir(home: Path) -> Path:
    return home / ".claude" / "rules"


@pytest.fixture
def hook_delivered_rule(home: Path) -> str:
    return _manifest_rules("hook-deliver", home)[0]


@pytest.fixture
def linked_rule(home: Path) -> str:
    return _manifest_rules("symlink", home)[0]


def _plant_link(rules_dir: Path, rel_path: str, target: Path) -> None:
    link = rules_dir / rel_path
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target)


def test_check_passes_rule_links_the_installer_made(home, tmp_path):
    output = _check(home, tmp_path)

    assert "rules linked, matching the manifest" in output, output
    assert "Rule links differ from the manifest" not in output


def test_check_fails_on_a_link_to_a_hook_delivered_rule(
    home, rules_dir, hook_delivered_rule, tmp_path
):
    _plant_link(rules_dir, hook_delivered_rule, RULES_SOURCE / hook_delivered_rule)

    output = _check(home, tmp_path)

    assert f"Stale rule link: {hook_delivered_rule}" in output, output
    assert "Rule links differ from the manifest — run: bash install.sh --relink" in output


def test_check_fails_on_a_manifest_rule_left_unlinked(home, rules_dir, linked_rule, tmp_path):
    (rules_dir / linked_rule).unlink()

    output = _check(home, tmp_path)

    assert f"Missing rule link: {linked_rule}" in output, output


def test_check_counts_a_dangling_link_as_missing(home, rules_dir, linked_rule, tmp_path):
    (rules_dir / linked_rule).unlink()
    _plant_link(rules_dir, linked_rule, tmp_path / "gone.md")

    output = _check(home, tmp_path)

    assert f"Missing rule link: {linked_rule}" in output, output


def test_check_fails_on_a_link_into_an_older_plugin_versions_rules(
    home, rules_dir, hook_delivered_rule, tmp_path
):
    older_rules = (
        home / ".claude" / "plugins" / "cache" / "bit-agora" / "praxion" / "0.1.0" / "rules"
    )
    (older_rules / hook_delivered_rule).parent.mkdir(parents=True)
    (older_rules / hook_delivered_rule).write_text("## A rule an older version linked\n")
    _plant_link(rules_dir, hook_delivered_rule, older_rules / hook_delivered_rule)

    output = _check(home, tmp_path)

    assert f"Stale rule link: {hook_delivered_rule}" in output, output


def test_check_leaves_a_link_outside_the_rules_source_alone(home, rules_dir, tmp_path):
    foreign = tmp_path / "foreign-rule.md"
    foreign.write_text("## A rule another tool installed\n")
    _plant_link(rules_dir, "other-tool/foreign-rule.md", foreign)

    output = _check(home, tmp_path)

    assert "rules linked, matching the manifest" in output, output
    assert "Stale rule link" not in output


def test_check_names_the_rules_the_sweep_removes(home, rules_dir, hook_delivered_rule, tmp_path):
    _plant_link(rules_dir, hook_delivered_rule, RULES_SOURCE / hook_delivered_rule)
    named = _shared(f'stale_rule_symlinks "{RULES_SOURCE}" "$HOME/.claude/rules"', home).split()

    _shared(f'sweep_stale_rule_symlinks "{RULES_SOURCE}" "$HOME/.claude/rules"', home)

    assert named == [str(rules_dir / hook_delivered_rule)]
    assert not (rules_dir / hook_delivered_rule).is_symlink()
