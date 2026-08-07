#!/usr/bin/env python3
"""Parse the YAML frontmatter of every shipped artifact -- with a real parser.

Nothing in this repository parsed command, agent, skill, or rule frontmatter.
The checks that exist -- the sentinel's ``C04``/``S01``/``S02`` -- grep for
field *presence*, and a grep for ``description:`` succeeds on a file no YAML
loader can read.  That is verbatim the anti-pattern
``rules/swe/gate-liveness.md`` names: *"Check asserts a section/field exists ->
passes on an empty section -- a hollow artifact looks complete."*

The defect that shipped: two command files carried

    argument-hint: [<run_tag>] [--task-slug <slug>]

Unquoted, that is two flow sequences on one line, which no YAML parser accepts.
The whole frontmatter block therefore failed to load, and a command whose
frontmatter does not load cannot register its ``description`` -- the sole
model-invocation mechanism.  Every presence-grep in the repo was green
throughout.

**Scope fidelity.**  The contract is narrow and deliberately so: *if a file
declares frontmatter, that frontmatter must load and must be a mapping.*  A
file with no frontmatter at all is counted and skipped, never flagged --
whether a given artifact class is *required* to carry frontmatter, and which
fields it must hold, is the sentinel's question, not this one's.  Splitting it
that way keeps this gate's computed scope equal to its documented scope.

**One named exception, and it is an exception rather than a widened rule.**
``argument-hint`` must load as a ``str``.  This is deliberately *not* a general
"declared fields must carry their contracted type" principle -- such a rule
would grow without bound and pull the sentinel's question back in here.  The
field earns its own assertion for a reason no other field currently shares:
the corpus is read by **two parser classes that disagree**.  The Cursor and
Codex exporters parse frontmatter line-by-line with a regex and coerce every
value to ``str``, so they never error; Claude Code and this gate use a real
YAML loader, which sees ``argument-hint: [--init]`` as a one-element *list*.
The divergence is therefore invisible from either side alone -- which is how
21 string-valued and 15 list-valued hints coexisted unnoticed.  It is also the
near-miss of the defect above: a multi-group hint in bracket form is two flow
sequences on one line, i.e. ``unparseable``, one edit away.  Asserting the type
is mechanically decidable and closes the class; the enumeration stays at one
field until a second one demonstrates the same two-reader divergence.

Four finding kinds:

``no-closing-delimiter``
    The file opens with ``---`` and never closes the block.  Every downstream
    reader then treats prose as YAML or the whole block as body text.

``unparseable``
    A real YAML parser rejects the block.  The finding carries the parser's own
    message, including the offending line and column.

``not-a-mapping``
    The block loads but yields a scalar, a list, or nothing.  Field lookup on a
    non-mapping silently returns nothing rather than raising, so this shape
    reads as "no fields declared" to every consumer.

``argument-hint-not-a-string``
    ``argument-hint`` loads as a list rather than a string.  See the scope note
    below for why this one field earns a type assertion here.

**PyYAML dependency (gate-liveness GL05).**  This gate needs a real parser, and
a hand-rolled one would be free to disagree with the loader it stands in for --
a gate that can differ from the thing it certifies is not a gate.  So the
dependency is kept and made honest on both ends: the ``.pre-commit-config.yaml``
hook declares ``language: python`` with ``additional_dependencies: ['pyyaml']``
(the invocation path resolves an interpreter that has it, matching the two
sibling hooks with the same need), and the import is deferred behind
``_require_yaml`` so a bare ``python3`` run *raises naming ``sys.executable``*
instead of dying on import or, worse, reporting clean.  A gate that cannot load
is indistinguishable from no gate; a gate that reports clean because it could
not read its input is worse than none.

Exit codes: 0 clean, 1 findings, 2 script error (including a missing parser).

Usage:
    python3 scripts/check_frontmatter_parses.py
    python3 scripts/check_frontmatter_parses.py --json
    python3 scripts/check_frontmatter_parses.py --repo-root PATH
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from _repo_root import resolve_repo_root

SCRIPT_DIR = Path(__file__).resolve().parent

# The artifact surfaces whose frontmatter is load-bearing at runtime: commands
# and agents register from it, skills gate activation on `description`, rules
# scope injection on `paths`. Globs (not a recursive `**/*.md`) because the
# nested `references/` and `assets/` files under `skills/` are prose, and a
# `README.md` in any of these directories carries no frontmatter by design.
SCAN_GLOBS: tuple[str, ...] = (
    "commands/*.md",
    "agents/*.md",
    "skills/*/SKILL.md",
    "rules/**/*.md",
)

# Opening `---` on its own line, the block, then a closing `---` on its own
# line. Matched against the file head only -- a `---` horizontal rule later in
# the body must never be mistaken for a delimiter.
_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.DOTALL)
_OPENS_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\n")


class MissingParserError(RuntimeError):
    """Raised when PyYAML is absent from the running interpreter.

    A distinct type, not a bare `ImportError`: the caller must be able to
    separate "cannot read the input" from "read the input and found nothing
    wrong". Collapsing the two is how a gate reports a false all-clear.
    """


@dataclass(frozen=True)
class Finding:
    """One artifact whose declared frontmatter does not load as a mapping."""

    kind: str
    file: str
    detail: str


def _require_yaml() -> Any:
    """Import PyYAML, or raise naming the interpreter that lacks it.

    Deferred rather than module-level so this file stays *importable* under an
    interpreter without PyYAML: a module-level import turns a missing package
    into an unreadable traceback at load, whereas this raises a message a reader
    can act on. `sys.executable` is named because the cause is almost always an
    invocation under the wrong interpreter, not an uninstalled package.
    """
    try:
        import yaml
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised via canary
        raise MissingParserError(
            f"PyYAML is required to parse frontmatter, and {sys.executable} does not "
            f"have it. Run under the project environment (e.g. `uv run --with pyyaml "
            f"python {Path(__file__).name}`) or install pyyaml into the interpreter "
            f"above. Refusing to report a verdict without a parser."
        ) from exc
    return yaml


def scan_targets(root: Path) -> list[Path]:
    """Every artifact file in scope, de-duplicated and ordered."""
    seen: dict[Path, None] = {}
    for glob in SCAN_GLOBS:
        for path in sorted(root.glob(glob)):
            if path.is_file():
                seen.setdefault(path, None)
    return list(seen)


def _first_error_line(exc: Exception) -> str:
    """Collapse a multi-line parser error into one informative line.

    PyYAML's `MarkedYAMLError` renders as four lines (context, context mark,
    problem, problem mark). The problem mark carries the offending line and
    column, which is the part a reader needs; joining them keeps the finding
    one row wide without discarding it.
    """
    parts = [line.strip() for line in str(exc).splitlines() if line.strip()]
    return " | ".join(parts) if parts else exc.__class__.__name__


def inspect_file(path: Path, root: Path) -> Finding | None:
    """Return a Finding for `path`, or None when it is clean or has no frontmatter."""
    rel = path.relative_to(root).as_posix()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return Finding("unreadable", rel, str(exc))

    if not _OPENS_FRONTMATTER_RE.match(text):
        return None

    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return Finding(
            "no-closing-delimiter",
            rel,
            "file opens with `---` but no closing `---` delimiter was found",
        )

    yaml = _require_yaml()
    try:
        loaded = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        return Finding("unparseable", rel, _first_error_line(exc))

    if not isinstance(loaded, dict):
        kind = type(loaded).__name__ if loaded is not None else "empty"
        return Finding(
            "not-a-mapping",
            rel,
            f"frontmatter loads as {kind}, not a mapping of fields",
        )

    hint = loaded.get("argument-hint")
    if hint is not None and not isinstance(hint, str):
        return Finding(
            "argument-hint-not-a-string",
            rel,
            f"argument-hint loads as {type(hint).__name__}, not str: {hint!r} "
            "-- quote the value; an unquoted '[x]' is a YAML flow sequence",
        )
    return None


def check_frontmatter_parses(root: Path) -> dict[str, Any]:
    """Scan every in-scope artifact and report frontmatter that does not load."""
    targets = scan_targets(root)
    findings: list[Finding] = []
    with_frontmatter = 0
    for path in targets:
        if _OPENS_FRONTMATTER_RE.match(path.read_text(encoding="utf-8", errors="replace")):
            with_frontmatter += 1
        finding = inspect_file(path, root)
        if finding is not None:
            findings.append(finding)
    return {
        "scanned": len(targets),
        "with_frontmatter": with_frontmatter,
        "skipped_no_frontmatter": len(targets) - with_frontmatter,
        "findings": [asdict(f) for f in findings],
    }


def _render_human(report: dict[str, Any]) -> str:
    lines = [
        f"Scanned {report['scanned']} artifact(s); "
        f"{report['with_frontmatter']} declare frontmatter, "
        f"{report['skipped_no_frontmatter']} do not."
    ]
    if not report["findings"]:
        lines.append("  all declared frontmatter loads as a mapping")
        return "\n".join(lines)
    for finding in report["findings"]:
        lines.append(f"  {finding['kind']}: {finding['file']}")
        lines.append(f"    {finding['detail']}")
    lines.append(
        f"\n{len(report['findings'])} artifact(s) ship frontmatter that does not load. "
        "A field-presence grep passes on these; no consumer can read them."
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Parse the YAML frontmatter of every shipped artifact with a real parser."
    )
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    parser.add_argument("--repo-root", help="repository root (defaults to git discovery)")
    args = parser.parse_args(argv)

    try:
        report = check_frontmatter_parses(resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR))
    except MissingParserError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(report, indent=2) if args.json else _render_human(report))
    return 1 if report["findings"] else 0


if __name__ == "__main__":
    sys.exit(main())
