"""Driver for the audience split of what a spawn receives from rule delivery.

What a scenario observes, all from outside the hooks:

* **Delivery.** The harness announces a session (`SessionStart`) or a spawn (`SubagentStart`)
  by running every command `hooks/hooks.json` registers for the event (a group's matcher is
  tested against `source` or `agent_type`), each as its own process with the event as one JSON
  object on stdin and `CLAUDE_PLUGIN_ROOT` naming the plugin root. Only synchronous commands
  deliver context; what reaches the agent is the `hookSpecificOutput.additionalContext` string
  each prints. A *rule delivery* is the list of those strings that open with the rule label
  (`## Praxion Rules (auto-injected): <unit>, part k of n`), plus the rule injector's own notice
  to a session (a string opening `## Praxion rule`, the label's prefix), in registration order.
* **Units.** A delivered string is its label line, one blank line, then its piece of the unit;
  a unit's text is its pieces joined in label order. A unit's *source text* is its rule file
  with the frontmatter block (and the blank lines that follow it) removed.
* **The split oracle.** `split_text` is the specification's split text, computed here from the
  source and the audience manifest alone: each section (heading levels two to four, outside
  fences) runs from its heading line to the line before the next such heading; a part runs from
  the one line its prefix begins to the next part or the section's end; an `orchestrator-only`
  section or part is removed, a section all of whose parts are removed goes heading and all,
  and every other byte stays. When the manifest cannot classify the unit exactly (absent,
  unparseable, a section or part without exactly one entry, an entry naming nothing, an unknown
  scope) there is no split text and only the whole unit is acceptable.
* **The base.** "As at the pipeline base" is observed, never remembered: `base_hooks_arm` is
  the tree under test with `hooks/` (the registration included) taken from the base commit, so
  it delivers the tree's own rule text the way the base delivered it (the whole unit, by the
  specification's definition); `base_tree_arm` also takes the base commit's rules, agent
  definitions, kernels and adoption ledger, for claims about strings that must not move at all.

Where a delivered string writes out the plugin root, it reads as `<plugin-root>`, so two
checkouts in different directories compare like with like.

Isolation: `kernel_sandbox.isolated_env` (own HOME, a `python3` shim for this interpreter, no
inherited `CLAUDE*`, `PRAXION_*`, `GIT_*` or `ANTHROPIC_*` variable). A user agent lives in that
HOME's `.claude/agents/`. A missing PyYAML is a `yaml` package first on `PYTHONPATH` whose import
fails, so the hooks' interpreter cannot import the parser.

Bound here: the delivery, the oracle, the base arms and the commit-time kernel gate (through
`kernel_sandbox.commit_gate`, which runs the `.pre-commit-config.yaml` hooks naming the kernel
checkers). The regeneration a maintainer runs after editing a rule or the audience manifest is
bound provisionally to the kernel generator. Unbound: the command that counts the text a split
recipient sheds.
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path

import yaml

from tests.acceptance.drivers.kernel_sandbox import (
    AUDIENCE_MANIFEST,
    GateVerdict,
    Sandbox,
    UnboundDriverError,
    commit_gate,
    isolated_env,
    normalize_plugin_location,
    regenerate,
)
from tests.acceptance.drivers.kernel_spawn import project_checkout

REPO_ROOT = Path(__file__).resolve().parents[3]
BASE_COMMIT = "f1f8adf18d18967c368c1a70f35132650802cde0"

RULES_MANIFEST = "rules/_manifest.yaml"
KILL_SWITCH = "PRAXION_DISABLE_RULE_INJECTION"
INLINE_CAP = 10_000
LABEL = re.compile(r"^## Praxion Rules \(auto-injected\): (\S+), part (\d+) of (\d+)$")
_RULE_DELIVERY_PREFIX = "## praxion rule"  # the label's prefix, compared case-insensitively

DROPPED = "orchestrator-only"
SCOPES = frozenset({"core", "role", DROPPED, "no-actor"})

# What the base commit's delivery reads, for `base_tree_arm`.
_BASE_DELIVERY_PATHS = (
    "hooks",
    "rules",
    "agents",
    "claude/kernels",
    ".ai-state/kernel_adoption.yaml",
)


@dataclass(frozen=True)
class Unit:
    id: str
    source: str


PROTOCOL = Unit(
    "swe/swe-agent-coordination-protocol", "rules/swe/swe-agent-coordination-protocol.md"
)
INTERMEDIATE = Unit("swe/agent-intermediate-documents", "rules/swe/agent-intermediate-documents.md")
ADR_RESIDENT = Unit("swe/adr-conventions-resident", "rules/swe/adr-conventions-resident.md")
SPLIT_UNITS = (PROTOCOL, INTERMEDIATE)
CORE_UNITS = (PROTOCOL, INTERMEDIATE, ADR_RESIDENT)

SPLIT_ROLES = (
    "agentic-transactions-architect",
    "architect-validator",
    "cicd-engineer",
    "context-engineer",
    "discipline-consultant",
    "doc-engineer",
    "implementation-planner",
    "interface-designer",
    "promethean",
    "roadmap-cartographer",
    "sentinel",
    "skill-genesis",
    "verifier",
)
LEAN_ROLES = ("researcher", "implementer", "test-engineer", "systems-architect")


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


# -- The specification's split text ------------------------------------------------------------

_HEADING = re.compile(r"^(#{2,4})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


def _body(text: str) -> str:
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end >= 0:
            text = text[end + len("\n---\n") :]
    return text.lstrip("\n")


def source_text(root: Path, unit: Unit) -> str:
    """The unit as rule delivery reads it: its file without the frontmatter block."""
    return _body((root / unit.source).read_text(encoding="utf-8"))


@dataclass(frozen=True)
class _Span:
    heading: str
    start: int  # the heading line
    end: int  # one past the section's last line


def _sections(lines: list[str]) -> list[_Span]:
    heads: list[tuple[int, str]] = []
    fenced = False
    for i, line in enumerate(lines):
        if _FENCE.match(line):
            fenced = not fenced
            continue
        match = None if fenced else _HEADING.match(line.rstrip("\n"))
        if match:
            heads.append((i, match.group(2)))
    return [
        _Span(heading, start, heads[k + 1][0] if k + 1 < len(heads) else len(lines))
        for k, (start, heading) in enumerate(heads)
    ]


def audience_entries(root: Path, unit: Unit) -> list[dict] | None:
    """The audience manifest's entries for `unit`; None when the manifest cannot be read."""
    try:
        manifest = yaml.safe_load((root / AUDIENCE_MANIFEST).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, UnicodeDecodeError):
        return None
    entries = manifest.get("entries") if isinstance(manifest, dict) else None
    if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
        return None
    return [e for e in entries if e.get("source") == unit.source]


def split_text(root: Path, unit: Unit) -> str | None:
    """The unit's text with exactly its orchestrator-only spans removed; None if undefined."""
    entries = audience_entries(root, unit)
    if entries is None:
        return None
    lines = source_text(root, unit).splitlines(keepends=True)
    sections = _sections(lines)
    headings = [s.heading for s in sections]
    by_heading: dict[str, list[dict]] = {}
    for entry in entries:
        by_heading.setdefault(entry.get("heading"), []).append(entry)
    if len(set(headings)) != len(headings) or set(by_heading) != set(headings):
        return None
    dropped = [False] * len(lines)

    def drop(start: int, end: int) -> None:
        for i in range(start, end):
            dropped[i] = True

    for section in sections:
        found = by_heading[section.heading]
        if any(e.get("scope") not in SCOPES for e in found):
            return None
        whole = [e for e in found if not e.get("part")]
        parts = [e for e in found if e.get("part")]
        if (whole and parts) or len(whole) > 1:
            return None
        if whole:
            if whole[0]["scope"] == DROPPED:
                drop(section.start, section.end)
            continue
        starts = []
        for entry in parts:
            prefix = str(entry["part"])
            hits = [i for i in range(section.start + 1, section.end) if lines[i].startswith(prefix)]
            if len(hits) != 1:
                return None
            starts.append((hits[0], entry["scope"]))
        starts.sort()
        if len({i for i, _ in starts}) != len(starts):
            return None
        if all(scope == DROPPED for _, scope in starts):
            drop(section.start, section.end)
            continue
        for k, (start, scope) in enumerate(starts):
            if scope == DROPPED:
                drop(start, starts[k + 1][0] if k + 1 < len(starts) else section.end)
    return "".join(line for line, gone in zip(lines, dropped, strict=True) if not gone).lstrip("\n")


def dropped_headings(root: Path, unit: Unit) -> list[str]:
    """Headings of the sections the manifest classifies orchestrator-only as a whole."""
    entries = audience_entries(root, unit) or []
    return [e["heading"] for e in entries if not e.get("part") and e.get("scope") == DROPPED]


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


# -- Editing a plugin checkout ----------------------------------------------------------------

PLANTED = "A sentence planted after the spawn delivery was last brought up to date."


def insert_under_heading(sandbox: Sandbox, unit: Unit, heading: str, text: str = PLANTED) -> None:
    """Put a new paragraph right under a section's heading line."""
    lines = sandbox.read(unit.source).splitlines(keepends=True)
    matches = [
        i
        for i, ln in enumerate(lines)
        if (m := _HEADING.match(ln.rstrip("\n"))) and m.group(2) == heading
    ]
    assert len(matches) == 1, f"{unit.source} has no single section headed {heading!r}"
    lines.insert(matches[0] + 1, f"\n{text}\n")
    sandbox.write(unit.source, "".join(lines))


def _entry_block(lines: list[str], source: str, heading: str) -> tuple[int, int]:
    """(first, end) line indices of the manifest entry for a whole section."""
    for i, line in enumerate(lines[:-1]):
        if line.strip() == f"- source: {source}" and lines[i + 1].strip() in (
            f'heading: "{heading}"',
            f"heading: {heading}",
        ):
            end = i + 2
            while (
                end < len(lines)
                and lines[end].startswith("    ")
                and not lines[end].lstrip().startswith("- ")
            ):
                end += 1
            block = lines[i:end]
            assert not any(ln.strip().startswith("part:") for ln in block), (
                f"the entry for {heading!r} is a part; give a whole-section heading"
            )
            return i, end
    raise AssertionError(f"{AUDIENCE_MANIFEST} has no whole-section entry for {source} {heading!r}")


def reclassify(
    sandbox: Sandbox,
    unit: Unit,
    heading: str,
    scope: str,
    *,
    reason: str | None = None,
    form: str | None = None,
) -> None:
    """Give a whole section a new scope (and the reason or form that scope asks for)."""
    lines = sandbox.read(AUDIENCE_MANIFEST).splitlines(keepends=True)
    first, end = _entry_block(lines, unit.source, heading)
    block = [f"  - source: {unit.source}\n", f'    heading: "{heading}"\n', f"    scope: {scope}\n"]
    if form:
        block.append(f"    form: {form}\n")
    if reason:
        block.append(f'    reason: "{reason}"\n')
    sandbox.write(AUDIENCE_MANIFEST, "".join(lines[:first] + block + lines[end:]))


def add_dropped_section(sandbox: Sandbox, unit: Unit, heading: str) -> None:
    """Append a new orchestrator-only section to the unit and classify it."""
    sandbox.append(unit.source, f"### {heading}\n\n{PLANTED}\n")
    sandbox.append(
        AUDIENCE_MANIFEST,
        f"  - source: {unit.source}\n"
        f'    heading: "{heading}"\n'
        f"    scope: {DROPPED}\n"
        '    reason: "A section planted for the drift canary."\n',
    )


def remove_section(sandbox: Sandbox, unit: Unit, heading: str) -> None:
    """Delete a whole section from the unit and its manifest entry."""
    lines = sandbox.read(unit.source).splitlines(keepends=True)
    body_offset = len(lines) - len(source_text(sandbox.root, unit).splitlines(keepends=True))
    spans = [s for s in _sections(lines[body_offset:]) if s.heading == heading]
    assert len(spans) == 1, f"{unit.source} has no single section headed {heading!r}"
    start, end = spans[0].start + body_offset, spans[0].end + body_offset
    sandbox.write(unit.source, "".join(lines[:start] + lines[end:]))
    manifest = sandbox.read(AUDIENCE_MANIFEST).splitlines(keepends=True)
    first, stop = _entry_block(manifest, unit.source, heading)
    sandbox.write(AUDIENCE_MANIFEST, "".join(manifest[:first] + manifest[stop:]))


def bring_up_to_date(root: Path) -> None:
    """The regeneration a maintainer runs after editing a rule or the audience manifest.

    Provisionally the kernel generator, the one regeneration step that exists today: the
    spawn delivery is assumed to come back into agreement through the same command.
    """
    regenerate(root)


def snapshot(sandbox: Sandbox) -> dict[str, bytes]:
    """Every file of the checkout a plant may touch or regenerate, by path."""
    return {
        str(p.relative_to(sandbox.root)): p.read_bytes()
        for top in ("rules", "claude", "agents", "hooks")
        for p in sorted((sandbox.root / top).rglob("*"))
        if p.is_file()
    }


def restore(sandbox: Sandbox, before: dict[str, bytes]) -> None:
    """Put the checkout back to `before`: files written back, files a plant added removed."""
    for rel in set(snapshot(sandbox)) - set(before):
        sandbox.path(rel).unlink()
    for rel, data in before.items():
        sandbox.path(rel).parent.mkdir(parents=True, exist_ok=True)
        sandbox.path(rel).write_bytes(data)


def changed_data_files(root: Path = REPO_ROOT) -> list[str]:
    """Plugin data files (no code, no registration, no source rule) added or changed since the base."""
    changed = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "diff",
            "--name-only",
            BASE_COMMIT,
            "--",
            "claude",
            "rules",
            "hooks",
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout.split()
    untracked = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "ls-files",
            "--others",
            "--exclude-standard",
            "--",
            "claude",
            "rules",
            "hooks",
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout.split()
    sources = {u.source for u in CORE_UNITS}
    return sorted(
        rel
        for rel in set(changed) | set(untracked)
        if (root / rel).is_file()
        and not rel.endswith(".py")
        and rel != "hooks/hooks.json"
        and rel not in sources
        and not re.search(r"(?:^|/)test_[^/]*$", rel)
    )


def damage(sandbox: Sandbox, rel: str, how: str) -> None:
    """Make a data file of the plugin missing, unreadable to a parser, or cut short."""
    path = sandbox.path(rel)
    if how == "missing":
        path.unlink()
    elif how == "garbage":
        path.write_bytes(b"\x00\xff not what was written here {[\n")
    elif how == "truncated":
        data = path.read_bytes()
        path.write_bytes(data[: len(data) // 2])
    else:
        raise ValueError(how)


def unreadable(path: Path) -> None:
    os.chmod(path, 0)


# -- The drift check ---------------------------------------------------------------------------


def kernel_gate(root: Path) -> GateVerdict:
    """The commit-time kernel checks, as `.pre-commit-config.yaml` registers them."""
    return commit_gate(root)


def names_unit(output: str, unit: Unit) -> bool:
    return unit.id in output or unit.source in output


@dataclass(frozen=True)
class DriftReading:
    disagreeing: tuple[str, ...]  # units a split recipient receives other than as split text
    refused: bool  # the commit-time kernel checks refused the tree
    named: tuple[str, ...]  # units the checks' output names
    output: str


def drift_reading(
    sandbox: Sandbox, project: Path, recipient: str = "praxion:verifier"
) -> DriftReading:
    """What a split recipient receives in `sandbox`, set against the kernel gate's verdict."""
    delivery = spawn(sandbox.root, project, recipient)
    disagreeing = tuple(
        u.id
        for u in SPLIT_UNITS
        if delivery.text_of(u) is None or delivery.text_of(u) != split_text(sandbox.root, u)
    )
    verdict = kernel_gate(sandbox.root)
    named = tuple(u.id for u in SPLIT_UNITS if names_unit(verdict.output, u))
    return DriftReading(
        disagreeing, verdict.refused, named if verdict.refused else (), verdict.output
    )


# Each kind of disagreement a split recipient's delivery can carry, planted in a checkout. A
# plant that changes kernel text regenerates the kernels, so no other kernel check has cause to
# refuse the tree; one that changes only text no kernel carries leaves the tree as edited.
PLANTS = (
    "dropped-span-edited-in-the-protocol",
    "dropped-span-edited-in-the-intermediate-documents-rule",
    "kept-span-edited-in-the-protocol",
    "kept-span-edited-in-the-intermediate-documents-rule",
    "dropped-section-reclassified-as-kept",
    "kept-section-reclassified-as-dropped",
    "dropped-section-added",
    "dropped-section-removed",
)


def plant(sandbox: Sandbox, name: str) -> Unit:
    """Apply one plant; returns the unit it touches."""
    if name == "dropped-span-edited-in-the-protocol":
        insert_under_heading(sandbox, PROTOCOL, "Available Agents")
        return PROTOCOL
    if name == "dropped-span-edited-in-the-intermediate-documents-rule":
        insert_under_heading(sandbox, INTERMEDIATE, "Document Lifecycle")
        return INTERMEDIATE
    if name == "kept-span-edited-in-the-protocol":
        insert_under_heading(sandbox, PROTOCOL, "Delegation Checklists")
        regenerate(sandbox.root)
        return PROTOCOL
    if name == "kept-span-edited-in-the-intermediate-documents-rule":
        insert_under_heading(sandbox, INTERMEDIATE, "`.ai-work/` — Ephemeral Pipeline Documents")
        regenerate(sandbox.root)
        return INTERMEDIATE
    if name == "dropped-section-reclassified-as-kept":
        reclassify(
            sandbox,
            PROTOCOL,
            "Available Agents",
            "no-actor",
            reason="The roster, kept for every reader.",
        )
        return PROTOCOL
    if name == "kept-section-reclassified-as-dropped":
        reclassify(
            sandbox,
            PROTOCOL,
            "Delegation Checklists",
            DROPPED,
            reason="Delegation is the main session's.",
        )
        regenerate(sandbox.root)
        return PROTOCOL
    if name == "dropped-section-added":
        add_dropped_section(sandbox, PROTOCOL, "Planted Orchestration Notes")
        return PROTOCOL
    if name == "dropped-section-removed":
        remove_section(sandbox, PROTOCOL, "Background Agents")
        return PROTOCOL
    raise ValueError(name)


# Plants that change only the touched unit's source, never the manifest: the other unit's
# split stands on its own and must still be delivered as split text.
SOURCE_ONLY_PLANTS = PLANTS[:4]


def other_unit(unit: Unit) -> Unit:
    return INTERMEDIATE if unit == PROTOCOL else PROTOCOL


# -- The shed count (unbound) ------------------------------------------------------------------


@dataclass(frozen=True)
class UnitCount:
    whole_chars: int  # the strings a whole recipient receives for the unit, labels included
    split_chars: int  # the strings a split recipient receives for the unit, labels included
    difference: int
    tokens: int  # the shed text's token figure
    token_basis: str  # "tokenizer" or "estimate"


@dataclass(frozen=True)
class ShedCount:
    exit_code: int
    units: dict[str, UnitCount]  # by unit id, for both split units
    total: UnitCount


@dataclass(frozen=True)
class ModelRequestTrap:
    """A `claude` stand-in that records any call and exits 1, and proxies that reach nothing."""

    bin_dir: Path
    calls: Path

    @property
    def env(self) -> dict[str, str]:
        dead = "http://127.0.0.1:9"
        return {"HTTP_PROXY": dead, "HTTPS_PROXY": dead, "ALL_PROXY": dead, "NO_PROXY": ""}

    def recorded(self) -> list[str]:
        return self.calls.read_text(encoding="utf-8").splitlines() if self.calls.exists() else []


def model_request_trap(scratch: Path) -> ModelRequestTrap:
    bin_dir = scratch / "trap-bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    calls = scratch / "claude-calls.log"
    stand_in = bin_dir / "claude"
    stand_in.write_text(f'#!/bin/sh\necho "$@" >> "{calls}"\nexit 1\n', encoding="utf-8")
    stand_in.chmod(0o755)
    return ModelRequestTrap(bin_dir, calls)


def shed_count(plugin_root: Path, scratch: Path, trap: ModelRequestTrap | None = None) -> ShedCount:
    """Run the no-cost count of the text a split recipient sheds, over `plugin_root`.

    With a `trap`, the command runs with `trap.bin_dir` first on PATH and `trap.env` applied.
    """
    raise UnboundDriverError(
        "the command that counts, at no cost, the characters a split recipient sheds per unit "
        "and in total (whole, split, difference, and a token figure labelled with its basis) "
        "is not bound yet: bind its invocation and its report's shape here"
    )
