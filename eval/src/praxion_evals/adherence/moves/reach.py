"""What the hook-less hosts still reach of a moved rule: a lean arm may relocate text, never lose it there.

Cursor and Codex have no hook channel, so the only text they deliver is what their own rule
exports carry. This module runs both exporters over a tree into a throwaway directory and measures,
line by line, which ``###`` sections of the moved rule (as the checkout holds it) each host reaches:

- Cursor reaches a section when every non-blank line of it appears unchanged in a file the
  Cursor export wrote;
- Codex reaches it through a file its bridge manifest lists with a load other than ``exclude``,
  and *always-on* through a file the manifest lists in its always-on set.

A lean copy is refused when either host reaches less than the checkout does (section and host
named), or when Codex narrows an always-on listing to a path-scoped one. Both exporters read the
rule files and ignore the rules manifest, so a manifest-only change loses nothing and is accepted.

The remaining hole is a hook that delivers a section from text it embeds while a declaration claims
it reads a carried file. So each lean hook is run offline (``observe``) against a synthetic matching
tool call, and every line it emits must be in a file both exports carry; a hook that embeds its
own text fails whatever its declaration says. The exporters are the checkout's own, run read-only.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, get_args

from praxion_evals.adherence.moves import observe
from praxion_evals.adherence.moves.model import HookContext, MoveDeclaration

Host = Literal["cursor", "codex"]
HOSTS: tuple[Host, ...] = get_args(Host)

CURSOR_EXPORTER = "cursor/config/export-cursor-rules.py"
CODEX_EXPORTER = "codex/config/export-codex-rules-bridge.py"
CODEX_MANIFEST = "praxion/rules_manifest.json"
CODEX_EXCLUDED_LOAD = "exclude"
EXPORT_TIMEOUT_SECONDS = 120
STDERR_TAIL_CHARS = 300
RULES_ROOT = "rules"
SYNTHETIC_COMMAND = "git commit -m x"  # a staging or committing call, the shape the kits match

_SECTION = "### "
_HIGHER_HEADINGS = ("# ", "## ")
_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


class ReachError(ValueError):
    """A lean copy that reaches less than the checkout on a host; names the section and the host."""


@dataclass(frozen=True)
class Carried:
    """What one host's export carries of a tree, keyed by the rule's path inside the tree."""

    files: Mapping[str, Path]
    always_on: frozenset[str]  # Codex only; empty for Cursor, which loads nothing always-on


def require_reach(
    declaration: MoveDeclaration, checkout: Path, copy: Path, hook_scripts: Sequence[str]
) -> None:
    """Refuse ``copy`` when a hook-less host reaches less of the moved rule than ``checkout`` does."""
    rule = declaration.moved_rule.value
    sections = section_lines(_read(checkout / rule))
    if not sections:
        raise ReachError(f"{rule} holds no '{_SECTION.strip()}' section to measure reach by")
    with tempfile.TemporaryDirectory(prefix="moves-reach-") as scratch:
        today = _carried_by_host(checkout, checkout, Path(scratch) / "today")
        lean = _carried_by_host(copy, checkout, Path(scratch) / "lean")
        losses = [
            message
            for host in HOSTS
            for message in _losses(host, rule, sections, today[host], lean[host])
        ]
        if losses:
            raise ReachError("; ".join(losses))
        _require_hook_text_carried(declaration, copy, hook_scripts, lean)


def _carried_by_host(tree: Path, exporter_root: Path, scratch: Path) -> dict[Host, Carried]:
    scratch.mkdir(parents=True)
    return {host: carried(host, tree, exporter_root, scratch) for host in HOSTS}


def section_lines(text: str) -> dict[str, tuple[str, ...]]:
    """Each ``###`` section of a rule, by title: its non-blank lines, heading included."""
    sections: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in _FRONTMATTER.sub("", text, count=1).splitlines():
        if line.startswith(_SECTION):
            current = sections.setdefault(line.lstrip("#").strip(), [])
        elif line.startswith(_HIGHER_HEADINGS):
            current = None
        if current is not None and line.strip():
            current.append(line.rstrip())
    return {title: tuple(lines) for title, lines in sections.items()}


def carried(host: Host, tree: Path, exporter_root: Path, scratch: Path) -> Carried:
    """Run ``host``'s export (the exporter ``exporter_root`` holds) over ``tree`` into ``scratch``."""
    if host == "cursor":
        return _cursor_carried(tree, exporter_root, scratch)
    return _codex_carried(tree, exporter_root, scratch)


def reached(sections: Mapping[str, tuple[str, ...]], files: Iterable[Path]) -> frozenset[str]:
    """The sections every one of whose lines is unchanged in some file of ``files``."""
    held = _lines_of(files)
    return frozenset(title for title, lines in sections.items() if set(lines) <= held)


# -- What each host's export carries ----------------------------------------------------------


def _cursor_carried(tree: Path, exporter_root: Path, scratch: Path) -> Carried:
    out = scratch / "cursor"
    _export(exporter_root / CURSOR_EXPORTER, [str(tree), str(out)], scratch)
    files = {
        f"{RULES_ROOT}/{path.relative_to(out).as_posix()}": path
        for path in sorted(out.rglob("*.md"))
    }
    return Carried(files, frozenset())


def _codex_carried(tree: Path, exporter_root: Path, scratch: Path) -> Carried:
    out = scratch / "codex"
    arguments = ["--repo-root", str(tree), "--out-dir", str(out)]
    _export(exporter_root / CODEX_EXPORTER, arguments, scratch)
    try:
        manifest = json.loads((out / CODEX_MANIFEST).read_text(encoding="utf-8"))
        listed = [r for r in manifest["rules"] if r["codex_load"] != CODEX_EXCLUDED_LOAD]
        always_on_ids = set(manifest["always_on_rule_ids"])
        files = {r["relpath"]: tree / r["relpath"] for r in listed}
        always_on = frozenset(r["relpath"] for r in listed if r["id"] in always_on_ids)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ReachError(f"the Codex rules manifest cannot be read: {error!r}") from error
    return Carried(files, always_on)


def _export(exporter: Path, arguments: list[str], scratch: Path) -> None:
    # No bytecode: the exporter's helper modules must not leave caches in the checkout it sits in.
    environment = {"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        result = subprocess.run(
            [sys.executable, str(exporter), *arguments],
            cwd=scratch,
            env=environment,
            capture_output=True,
            text=True,
            timeout=EXPORT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ReachError(f"the export {exporter.name} could not run: {error!r}") from error
    if result.returncode != 0:
        tail = result.stderr.strip()[-STDERR_TAIL_CHARS:]
        raise ReachError(f"the export {exporter.name} exited {result.returncode}: {tail}")


# -- Comparing the lean copy with the checkout ------------------------------------------------


def _losses(
    host: Host, rule: str, sections: Mapping[str, tuple[str, ...]], today: Carried, lean: Carried
) -> list[str]:
    messages: list[str] = []
    lost = _titles(reached(sections, today.files.values()) - reached(sections, lean.files.values()))
    if lost:
        messages.append(f"the lean arm leaves {host} reaching less of {rule} than today: {lost}")
    narrowed = _titles(reached(sections, _always_on(today)) - reached(sections, _always_on(lean)))
    if narrowed:
        messages.append(f"the lean arm no longer reaches {narrowed} always-on on {host}")
    return messages


def _always_on(carried_files: Carried) -> list[Path]:
    return [carried_files.files[relpath] for relpath in carried_files.always_on]


def _titles(sections: Iterable[str]) -> str:
    return ", ".join(f'"{title}"' for title in sorted(sections))


# -- A hook may only deliver text a hook-less host also reaches -------------------------------


def _require_hook_text_carried(
    declaration: MoveDeclaration,
    copy: Path,
    hook_scripts: Sequence[str],
    lean: Mapping[Host, Carried],
) -> None:
    shared = set.intersection(*(set(lean[host].files) for host in HOSTS))
    allowed = _lines_of(lean["cursor"].files[relpath] for relpath in shared)
    for delivery in declaration.deliveries:
        if not isinstance(delivery, HookContext):
            continue
        for script in hook_scripts:
            for line in _emitted(copy, delivery, script):
                if line.rstrip() not in allowed:
                    raise ReachError(
                        f"the hook {script} delivers a line read from no rule file both "
                        f'{" and ".join(HOSTS)} carry, so those hosts never reach it: "{line.strip()}"'
                    )


def _emitted(copy: Path, delivery: HookContext, script: str) -> tuple[str, ...]:
    payload = {
        "tool_name": delivery.matcher.split("|")[0],
        "tool_input": {"command": SYNTHETIC_COMMAND},
    }
    observed = observe.hook_output(copy, delivery.event, payload, script=Path(script).name)
    if isinstance(observed, observe.Refused):
        raise ReachError(f"the hook {script} cannot be observed: {observed.reason}")
    return observed.lines


# -- Reading ----------------------------------------------------------------------------------


def _lines_of(files: Iterable[Path]) -> frozenset[str]:
    return frozenset(
        line.rstrip()
        for path in files
        if path.is_file()
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
    )


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, ValueError) as error:
        raise ReachError(f"{path} cannot be read: {error}") from error
