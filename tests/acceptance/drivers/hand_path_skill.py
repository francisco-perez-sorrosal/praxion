"""Driver for the hand path's skills, loaded and run as Claude Code loads and runs them.

Claude Code loads a plugin skill's body with every literal `${CLAUDE_PLUGIN_ROOT}` replaced by
the absolute path of the plugin's installed version, then runs the fenced `bash` blocks the body
gives it through its Bash tool, whose environment carries no `CLAUDE_PLUGIN_ROOT` unless the
person's own configuration exports one. This driver does both over a scratch machine: it
substitutes the root a scenario names (a path that is not a directory stands for "no substituted
root"), runs every `bash` block in order, each in a fresh `bash -x` with the machine's HOME, and
reads from the shell's trace which `install.sh` the blocks ran and with what arguments. What the
person reads is the loaded body and the blocks' output, the trace aside.

The plugin cache, the registry (`~/.claude/plugins/installed_plugins.json`) and the scratch HOME
are `plugin_update`'s machine. Nothing here imports the system under test.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from tests.acceptance.drivers import plugin_update as pu

REPO_ROOT = pu.REPO_ROOT
SKILLS = {"install": "praxion-complete-install", "uninstall": "praxion-complete-uninstall"}
PLACEHOLDER = "${CLAUDE_PLUGIN_ROOT}"
REGISTRY = Path(".claude/plugins/installed_plugins.json")
PLUGIN_KEY = "praxion@bit-agora"
NOT_FOUND = "Praxion plugin not found"
NOT_FOUND_UNINSTALL = "Praxion plugin not found — nothing to uninstall"
INSTALL_COMMAND = "claude plugin install praxion@bit-agora"

_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
_FENCE = re.compile(r"^[ \t]*```([\w-]*)[ \t]*\n(.*?)^[ \t]*```[ \t]*$", re.MULTILINE | re.DOTALL)


# -- The skill as Claude Code loads it ------------------------------------------------------------


def skill_file(skill: str) -> Path:
    return REPO_ROOT / "skills" / SKILLS[skill] / "SKILL.md"


def frontmatter_and_body(skill: str) -> tuple[str, str]:
    match = _FRONTMATTER.match(skill_file(skill).read_text(encoding="utf-8"))
    if not match:
        raise AssertionError(f"{skill_file(skill)} has no frontmatter block")
    return match.group(1), match.group(2)


def description(skill: str) -> str:
    import yaml

    return yaml.safe_load(frontmatter_and_body(skill)[0]).get("description") or ""


def loaded_body(skill: str, substituted: Path | str) -> str:
    """The body as the model receives it: each literal placeholder replaced by `substituted`."""
    return frontmatter_and_body(skill)[1].replace(PLACEHOLDER, str(substituted))


def bash_blocks(text: str) -> list[str]:
    return [content for lang, content in _FENCE.findall(text) if lang == "bash"]


def catalog_row(skill: str) -> str:
    """The description cell of the skill's row in `skills/README.md`."""
    text = (REPO_ROOT / "skills" / "README.md").read_text(encoding="utf-8")
    name = re.escape(SKILLS[skill])
    match = re.search(
        rf"^\|\s*\*\*\[{name}\]\([^)]*\)\*\*\s*\|\s*(.+?)\s*\|[^|]*\|\s*$", text, re.M
    )
    if not match:
        raise AssertionError(f"skills/README.md holds no row for {SKILLS[skill]}")
    return match.group(1)


# -- A machine with a plugin cache ----------------------------------------------------------------


def cache_of_versions(machine: pu.Machine, names: list[str], source: Path) -> dict[str, Path]:
    """One directory per version in the machine's cache, each a hard-linked copy of `source`."""
    made = {}
    for name in names:
        dest = machine.version(name)
        if not dest.exists():
            shutil.copytree(source, dest, copy_function=os.link)
        made[name] = dest
    return made


def checkout_elsewhere(machine: pu.Machine) -> Path:
    """A checkout outside the cache with an installer of its own, as a person's clone is."""
    checkout = machine.root / "a-checkout"
    checkout.mkdir(parents=True, exist_ok=True)
    installer = checkout / "install.sh"
    installer.write_text("#!/usr/bin/env bash\necho 'a checkout of its own'\n", encoding="utf-8")
    installer.chmod(0o755)
    return checkout


@dataclass(frozen=True)
class Entry:
    scope: str
    install_path: Path
    version: str


def register(machine: pu.Machine, entries: list[Entry] | None) -> None:
    """Write the registry with `entries` for the praxion plugin, in order; None removes it."""
    path = machine.home / REGISTRY
    if entries is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    listed = []
    for e in entries:
        item = {"scope": e.scope, "installPath": str(e.install_path), "version": e.version}
        if e.scope == "project":
            item["projectPath"] = str(machine.root / "work")
        listed.append(item)
    path.write_text(json.dumps({"version": 2, "plugins": {PLUGIN_KEY: listed}}), encoding="utf-8")


# -- Running the skill ----------------------------------------------------------------------------


@dataclass(frozen=True)
class SkillRun:
    shown: str  # the loaded body and every block's output: what the person and the model read
    calls: list[tuple[str, tuple[str, ...]]]  # each `install.sh` run: its directory, its arguments

    def checks(self) -> list[str]:
        """The directories whose `install.sh code --check` the blocks ran."""
        return [where for where, args in self.calls if "--check" in args]

    def names(self, directory: Path | str) -> bool:
        """`directory`'s path is written out where the person reads it."""
        return re.search(re.escape(str(directory)) + r"(?![\w.-])", self.shown) is not None


def run_skill(
    skill: str, machine: pu.Machine, *, substituted: Path | str, shell_root: Path | None = None
) -> SkillRun:
    """Load the skill with `substituted` for the placeholder and run its bash blocks in order.

    `shell_root` is a `CLAUDE_PLUGIN_ROOT` the shell carries from the person's own configuration;
    by default the shell carries none, as the Bash tool's does."""
    body = loaded_body(skill, substituted)
    env = machine.env()
    env["PS4"] = "+ "
    if shell_root is not None:
        env["CLAUDE_PLUGIN_ROOT"] = str(shell_root)
    shown, calls = [body], []
    for block in bash_blocks(body):
        result = subprocess.run(
            ["bash", "-x", "-c", block],
            cwd=machine.root / "work", env=env, capture_output=True, text=True, timeout=300,
        )  # fmt: skip
        trace = [line for line in result.stderr.splitlines() if line.startswith("+")]
        said = [line for line in result.stderr.splitlines() if not line.startswith("+")]
        shown += [result.stdout, "\n".join(said)]
        calls += [call for line in trace if (call := _installer_call(line))]
    return SkillRun("\n".join(shown), calls)


def _installer_call(trace_line: str) -> tuple[str, tuple[str, ...]] | None:
    try:
        words = shlex.split(trace_line.lstrip("+").strip())
    except ValueError:
        return None
    for i, word in enumerate(words):
        if os.path.basename(word) == "install.sh":
            return os.path.normpath(os.path.dirname(word)), tuple(words[i + 1 :])
    return None
