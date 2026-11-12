"""Plugin checkouts, projects and the rule delivery a session or a spawn receives.

The harness announces a session (`SessionStart`) or a spawn (`SubagentStart`) by running every
command `hooks/hooks.json` registers for the event (a group's matcher is tested against `source`
or `agent_type`), each as its own process with the event as one JSON object on stdin and
`CLAUDE_PLUGIN_ROOT` naming the plugin root. Only synchronous commands deliver context; what
reaches the agent is the `hookSpecificOutput.additionalContext` string each prints. A *rule
delivery* is the list of those strings that open with the rule label
(`## Praxion Rules (auto-injected): <unit>, part k of n`), plus the rule injector's own notice to a
session (a string opening `## Praxion rule`, the label's prefix), in registration order.

A delivered string is its label line, one blank line, then its piece of the unit; a unit's text is
its pieces joined in label order.

"As at the pipeline base" is observed, never remembered: `base_hooks_arm` is the tree under test
with `hooks/` (the registration included) taken from the base commit, so it delivers the tree's
own rule text the way the base delivered it (the whole unit, by the specification's definition);
`base_tree_arm` also takes the base commit's rules, agent definitions, kernels and adoption
ledger, for claims about strings that must not move at all.

Where a delivered string writes out the plugin root, it reads as `<plugin-root>`, so two checkouts
in different directories compare like with like.
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import tarfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml

from tests.acceptance.drivers.audience_split_oracle import Unit, split_text
from tests.acceptance.drivers.kernel_sandbox import isolated_env, normalize_plugin_location
from tests.acceptance.drivers.kernel_spawn import project_checkout
from tests.acceptance.drivers.process_text_oracles import Changes, unexplained_changes

REPO_ROOT = Path(__file__).resolve().parents[3]
BASE_COMMIT = "f1f8adf18d18967c368c1a70f35132650802cde0"

RULES_MANIFEST = "rules/_manifest.yaml"
KILL_SWITCH = "PRAXION_DISABLE_RULE_INJECTION"
INLINE_CAP = 10_000
LABEL = re.compile(r"^## Praxion Rules \(auto-injected\): (\S+), part (\d+) of (\d+)$")
_RULE_DELIVERY_PREFIX = "## praxion rule"  # the label's prefix, compared case-insensitively

# What the base commit's delivery reads, for `base_tree_arm`.
_BASE_DELIVERY_PATHS = (
    "hooks",
    "rules",
    "agents",
    "claude/kernels",
    ".ai-state/kernel_adoption.yaml",
)


# -- Plugin checkouts -------------------------------------------------------------------------


def base_commit_available() -> bool:
    probe = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "cat-file", "-e", f"{BASE_COMMIT}^{{commit}}"],
        capture_output=True,
        timeout=30,
    )
    return probe.returncode == 0


def _extract_base(paths: tuple[str, ...], dest: Path) -> None:
    archive = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "archive", "--format=tar", BASE_COMMIT, *paths],
        capture_output=True,
        check=True,
        timeout=120,
    )
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        tar.extractall(dest, filter="data")


def _replace_with_base(tree: Path, dest: Path, paths: tuple[str, ...]) -> Path:
    shutil.copytree(tree, dest, symlinks=True)
    for rel in paths:
        target = dest / rel
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        elif target.exists() or target.is_symlink():
            target.unlink()
    _extract_base(paths, dest)
    return dest


def changes_beyond_declared_edits(base: Sequence[str], delivered: Sequence[str]) -> Changes:
    """What `delivered` adds or loses against `base` that no declared edit accounts for; empty
    when the two are byte for byte equal.

    The base arm is a live read of the base commit's kernels, so a later change that edits a
    kernel and declares the edit in `project_gating/declared_edits.json` moves the delivery away
    from that commit by design. Such an edit is not a breach of the guard; any other difference
    is. The declared edits are read only when the two readings differ.
    """
    if tuple(delivered) == tuple(base):
        return Changes([], [])
    return unexplained_changes("\n\n".join(base), "\n\n".join(delivered))


def base_hooks_arm(tree: Path, dest: Path) -> Path:
    """`tree` delivered the way the base delivered it: its sources, the base commit's hooks."""
    return _replace_with_base(tree, dest, ("hooks",))


def base_tree_arm(tree: Path, dest: Path) -> Path:
    """`tree` with everything the base delivery reads taken from the base commit."""
    return _replace_with_base(tree, dest, _BASE_DELIVERY_PATHS)


# -- Projects ------------------------------------------------------------------------------------


def fresh_project(path: Path, *, managed: bool = True) -> Path:
    """A git working tree at `path`, emptied first so two arms see the very same project."""
    if path.exists():
        shutil.rmtree(path)
    return project_checkout(path, managed=managed)


def write_blacklist(project: Path, disable: list[str]) -> None:
    config = project / ".claude" / "praxion-rules.yaml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(yaml.safe_dump({"version": 1, "disable": disable}), encoding="utf-8")


def write_definition(directory: Path, name: str, *, lean: bool = False) -> None:
    """An agent definition named `name` under `directory` (a project's or a user's agents)."""
    directory.mkdir(parents=True, exist_ok=True)
    flag = "omitClaudeMd: true\n" if lean else ""
    (directory / f"{name}.md").write_text(
        f"---\nname: {name}\ndescription: an agent outside this plugin\n{flag}---\n\nBody.\n",
        encoding="utf-8",
    )


def user_agents_dir(scratch: Path) -> Path:
    return scratch / "home" / ".claude" / "agents"


def without_pyyaml(scratch: Path) -> dict[str, str]:
    """Environment under which the hooks' interpreter cannot import PyYAML."""
    shadow = scratch / "no-pyyaml" / "yaml"
    shadow.mkdir(parents=True, exist_ok=True)
    (shadow / "__init__.py").write_text(
        'raise ImportError("PyYAML is not installed for this interpreter")\n', encoding="utf-8"
    )
    return {"PYTHONPATH": str(shadow.parent)}


# -- Delivery -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Delivery:
    strings: tuple[str, ...]  # every synchronous command's additionalContext, in order

    @property
    def rule_strings(self) -> tuple[str, ...]:
        return tuple(s for s in self.strings if s.lower().startswith(_RULE_DELIVERY_PREFIX))

    @property
    def labelled(self) -> tuple[str, ...]:
        return tuple(s for s in self.strings if LABEL.match(s.partition("\n")[0]))

    def labels(self) -> list[tuple[str, int, int]]:
        found = []
        for s in self.labelled:
            match = LABEL.match(s.partition("\n")[0])
            assert match is not None
            found.append((match.group(1), int(match.group(2)), int(match.group(3))))
        return found

    def announced(self) -> list[tuple[str, int, int]]:
        """Every part the labels announce: for each unit in order, parts 1 to n of its n."""
        totals = dict.fromkeys(self.unit_order(), 0)
        for unit_id, _, n in self.labels():
            totals[unit_id] = max(totals[unit_id], n)
        return [(unit_id, k, n) for unit_id, n in totals.items() for k in range(1, n + 1)]

    def unit_order(self) -> list[str]:
        order: list[str] = []
        for unit_id, _, _ in self.labels():
            if unit_id not in order:
                order.append(unit_id)
        return order

    def unit_strings(self, unit: Unit) -> tuple[str, ...]:
        return tuple(
            s for s, (u, _, _) in zip(self.labelled, self.labels(), strict=True) if u == unit.id
        )

    def text_of(self, unit: Unit) -> str | None:
        """The unit's pieces joined in delivery order; None when no string carries it."""
        strings = self.unit_strings(unit)
        if not strings:
            return None
        pieces = []
        for s in strings:
            label, _, rest = s.partition("\n")
            assert rest.startswith("\n"), (
                f"a string of {unit.id} does not leave one blank line under its label "
                f"{label!r}: {rest[:60]!r}"
            )
            pieces.append(rest[1:])
        return "".join(pieces)


def _sync_commands(plugin_root: Path, event: str, value: str) -> list[tuple[str, int]]:
    groups = json.loads((plugin_root / "hooks" / "hooks.json").read_text())["hooks"].get(event, [])
    chosen = []
    for group in groups:
        matcher = group.get("matcher", "")
        if matcher not in ("", "*") and not re.fullmatch(matcher, value):
            continue
        chosen += [
            (hook["command"], int(hook.get("timeout", 60)))
            for hook in group["hooks"]
            if not hook.get("async", False)
        ]
    return chosen


def _context(stdout: str) -> str | None:
    try:
        parsed = json.loads(stdout)
    except ValueError:
        return None
    output = parsed.get("hookSpecificOutput") if isinstance(parsed, dict) else None
    text = output.get("additionalContext") if isinstance(output, dict) else None
    return text if isinstance(text, str) else None


def _announce(
    plugin_root: Path,
    event: str,
    payload: dict,
    match_value: str,
    project: Path,
    scratch: Path,
    env: dict[str, str] | None,
) -> Delivery:
    environment = isolated_env(
        scratch, CLAUDE_PLUGIN_ROOT=str(plugin_root), CLAUDE_PROJECT_DIR=str(project)
    )
    environment.update(env or {})
    strings = []
    for command, timeout in _sync_commands(plugin_root, event, match_value):
        try:
            proc = subprocess.run(
                ["/bin/sh", "-c", command],
                input=json.dumps(payload),
                cwd=project,
                env=environment,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            continue  # the harness drops a hook that outlives its registered timeout
        text = _context(proc.stdout)
        if text is not None:
            strings.append(normalize_plugin_location(text, plugin_root))
    return Delivery(tuple(strings))


def spawn(
    plugin_root: Path,
    project: Path,
    agent_type: str,
    *,
    scratch: Path | None = None,
    env: dict[str, str] | None = None,
) -> Delivery:
    """What a spawn of `agent_type` started in `project` receives at `SubagentStart`."""
    payload = {
        "session_id": "audience-split",
        "transcript_path": str(project.parent / "audience-split-session.jsonl"),
        "cwd": str(project),
        "hook_event_name": "SubagentStart",
        "agent_id": "agent-0001",
        "agent_type": agent_type,
    }
    scratch = scratch or project.parent / ".audience-split-scratch"
    return _announce(plugin_root, "SubagentStart", payload, agent_type, project, scratch, env)


def session_start(
    plugin_root: Path,
    project: Path,
    *,
    scratch: Path | None = None,
    env: dict[str, str] | None = None,
) -> Delivery:
    """What the main session receives at `SessionStart` (a fresh start) in `project`."""
    payload = {
        "session_id": "audience-split",
        "transcript_path": str(project.parent / "audience-split-session.jsonl"),
        "cwd": str(project),
        "hook_event_name": "SessionStart",
        "source": "startup",
    }
    scratch = scratch or project.parent / ".audience-split-scratch"
    return _announce(plugin_root, "SessionStart", payload, "startup", project, scratch, env)


# -- Impaired rule delivery --------------------------------------------------------------------

IMPAIRMENTS = (
    "kill-switch",
    "no-pyyaml",
    "rules-manifest-missing",
    "rules-manifest-unreadable",
    "rules-manifest-malformed",
    "rules-manifest-damaged-row",
)


def impair(root: Path, scratch: Path, how: str) -> dict[str, str]:
    """Put a plugin checkout in an impaired state; returns the environment that state needs."""
    manifest = root / RULES_MANIFEST
    if how == "unimpaired":
        return {}
    if how == "kill-switch":
        return {KILL_SWITCH: "1"}
    if how == "no-pyyaml":
        return without_pyyaml(scratch)
    if how == "rules-manifest-missing":
        manifest.unlink()
    elif how == "rules-manifest-unreadable":
        unreadable(manifest)
    elif how == "rules-manifest-malformed":
        manifest.write_text("rules: [\n  - {id: swe/unfinished\n", encoding="utf-8")
    elif how == "rules-manifest-damaged-row":
        with manifest.open("a", encoding="utf-8") as rows:
            rows.write("- id: 7\n  install: [hook-deliver, symlink]\n  core: maybe\n")
    else:
        raise ValueError(how)
    return {}


def delivered_as(delivery: Delivery, whole: Delivery, root: Path, unit: Unit) -> str:
    """ "split", "whole" or "neither": how `delivery` carries `unit` for the tree at `root`.

    `whole` is the base-delivery arm's reading of the same tree in the same state, so "whole"
    means the unit's strings are byte for byte those the base would deliver.
    """
    expected = split_text(root, unit)
    if expected is not None and delivery.text_of(unit) == expected:
        return "split"
    if delivery.unit_strings(unit) and delivery.unit_strings(unit) == whole.unit_strings(unit):
        return "whole"
    return "neither"


def unreadable(path: Path) -> None:
    os.chmod(path, 0)
