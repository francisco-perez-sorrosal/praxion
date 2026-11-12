"""The clone installer offers the machine's own identity, never one shipped in the installer.

`install_claude.sh` fills the personal identifiers of `~/.claude/CLAUDE.md` from defaults the
person accepts or edits. The defaults come from the machine running it, by the rule the
first-session hook uses: its git `user.email`, else an anonymous stand-in. Each run here is a
clone relink, or a dry run, from a stand-in clone into a scratch machine, so it renders into the
clone and never into this checkout or the operator's HOME.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from tests.acceptance.drivers import plugin_update as pu

INSTALLER = pu.REPO_ROOT / "install_claude.sh"
ANONYMOUS = {"USERNAME": "@anon", "EMAIL": "anon@unknown", "GITHUB_URL": "https://github.com/anon"}
PROBE = pu.Identity("Probe Person", "probe.person@example.invalid")
PROBE_VALUES = {
    "USERNAME": "@probe-person",
    "EMAIL": "probe.person@example.invalid",
    "GITHUB_URL": "https://github.com/probe-person",
}


@pytest.fixture
def clone(tmp_path):
    return pu.as_git_repository(pu.shipped_tree(tmp_path / "clone"))


def _machine(tmp_path, who: pu.Identity | None) -> pu.Machine:
    machine = pu.Machine(tmp_path / "machine")
    if who is not None:
        machine.set_identity(who)
    return machine


def _rendered_values(clone) -> dict[str, str]:
    template = (clone / pu.TEMPLATE).read_text(encoding="utf-8")
    return pu.values_in((clone / pu.RENDER).read_text(encoding="utf-8"), template)


@pytest.mark.parametrize(
    ("who", "expected"),
    [(PROBE, PROBE_VALUES), (None, ANONYMOUS)],
    ids=["git-identity", "no-git-identity"],
)
def test_accepting_the_defaults_renders_the_machines_own_identity(tmp_path, clone, who, expected):
    result = pu.relink(clone, _machine(tmp_path, who), answers="Y\nY\nY\n")
    assert result.returncode == 0, result.stdout[-1500:] + result.stderr[-1500:]
    assert _rendered_values(clone) == expected


def test_the_dry_run_shows_the_machines_own_identity_as_the_defaults(tmp_path, clone):
    result = subprocess.run(
        ["bash", str(clone / "install_claude.sh"), "code", "--dry-run"],
        cwd=clone, env=_machine(tmp_path, PROBE).env(), capture_output=True, text=True,
        timeout=300,
    )  # fmt: skip
    defaults = " / ".join(PROBE_VALUES[key] for key in ("USERNAME", "EMAIL", "GITHUB_URL"))
    assert f"Defaults: {defaults}" in result.stdout, result.stdout[-1500:] + result.stderr[-1500:]


def test_the_installer_ships_no_maintainers_identity():
    author = json.loads((pu.REPO_ROOT / ".claude-plugin" / "plugin.json").read_text())["author"]
    shipped = INSTALLER.read_text(encoding="utf-8")
    handle = "@" + author["email"].split("@")[0]
    held = [value for value in (author["email"], author["url"], handle) if value in shipped]
    assert not held, f"install_claude.sh holds the maintainer's identity: {held}"
