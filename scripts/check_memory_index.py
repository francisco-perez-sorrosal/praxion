#!/usr/bin/env python3
"""Keep Claude Code memory indexes what the harness loads them as: one-line pointers.

A memory index (``MEMORY.md``) is loaded into the start of every session, and
an agent's own index into every spawn of that agent, up to the harness's load
limit of the first 200 lines or 25 KB. Topic files load only when read. So the
index must stay a list of pointers -- ``- [Title](file.md) — hook`` -- with
status, history and detail living in the topic files. Left alone, indexes drift
into status logs: Praxion's own grew to 19.3 KB with lines of 1,225 characters,
weeks from the point where entries silently stop loading.

The convention, as data:

- an index line is blank, a markdown heading, or a pointer to a topic file in
  the same directory, at most ``MAX_LINE_CHARS`` characters long;
- every linked file exists, no file is linked twice, and every topic file in
  the directory is linked (an unlinked file is a dropped entry: shorten
  entries, never drop them);
- the index stays inside the harness load limit.

Two consumers share this module. ``hooks/guard_memory_index.py`` calls
``gate_messages`` before a Write or Edit lands and refuses one that *adds*
a violation, so existing debt never blocks unrelated work. This command audits
whole indexes: the current project's by default, every index under the Claude
config directory with ``--all``, or the paths given.

Declared limit: a write made through Bash (``printf >> MEMORY.md``) bypasses
the gate; the audit still sees its result.

Exit codes: 0 no failing finding, 1 at least one, 2 usage or read error.
Stdlib-only, because the hook and the ambient ``python3`` both run it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

CONFIG_DIR_VARIABLE = "CLAUDE_CONFIG_DIR"
INDEX_NAME = "MEMORY.md"

# The harness's own guidance for an index entry: one line, under ~150 characters.
MAX_LINE_CHARS = 150
# The harness loads the first 200 lines or 25 KB of an index, whichever is hit first.
LOAD_LINE_CAP = 200
LOAD_BYTE_CAP = 25_000
# The audit warns once an index passes this share of either cap.
NEAR_LIMIT_SHARE = 0.8

CONVENTION = (
    "A memory index holds one-line pointers of at most 150 characters, "
    "`- [Title](file.md) — hook`; status, history and detail go in the topic file."
)

_POINTER = re.compile(
    r"^- \[(?P<title>[^\]]+)\]\((?P<target>[^)\s]+)\)(?:\s+[—–-]\s+(?P<hook>\S.*))?$"
)
_HEADING = re.compile(r"^#{1,6}\s")


@dataclass(frozen=True)
class Finding:
    """One way an index departs from the convention; `line` is 0 for whole-index findings."""

    kind: str
    severity: str  # "fail" or "warn"
    line: int
    detail: str


def line_findings(text: str) -> list[Finding]:
    """Per-line findings: a line too long, or a line that is neither pointer, heading nor blank."""
    findings = []
    for number, line in enumerate(text.splitlines(), start=1):
        findings.extend(_judge_line(line, number))
    return findings


def _judge_line(line: str, number: int) -> list[Finding]:
    if not line.strip() or _HEADING.match(line):
        return []
    findings = []
    if len(line) > MAX_LINE_CHARS:
        findings.append(
            Finding("too-long", "fail", number, f"{len(line)} characters (max {MAX_LINE_CHARS})")
        )
    if not _POINTER.match(line):
        findings.append(
            Finding("not-a-pointer", "fail", number, f"content in the index: {line[:60]!r}")
        )
    return findings


def audit(index: Path) -> list[Finding]:
    """Every finding for one index: its lines, its links and its size."""
    text = index.read_text(encoding="utf-8")
    findings = line_findings(text)
    findings.extend(_link_findings(index, text))
    findings.extend(_size_findings(text))
    return findings


def _link_findings(index: Path, text: str) -> list[Finding]:
    targets: Counter[str] = Counter()
    findings = []
    for number, line in enumerate(text.splitlines(), start=1):
        match = _POINTER.match(line)
        if not match:
            continue
        target = match["target"]
        targets[target] += 1
        if targets[target] == 2:
            findings.append(Finding("duplicate", "fail", number, f"{target} is linked twice"))
        if not (index.parent / target).is_file():
            findings.append(Finding("dangling", "fail", number, f"{target} does not exist"))
    for topic in sorted(index.parent.glob("*.md")):
        if topic.name != INDEX_NAME and topic.name not in targets:
            findings.append(
                Finding("unindexed", "fail", 0, f"{topic.name} is not linked; add its pointer")
            )
    return findings


def _size_findings(text: str) -> list[Finding]:
    lines, size = len(text.splitlines()), len(text.encode("utf-8"))
    if lines > LOAD_LINE_CAP or size > LOAD_BYTE_CAP:
        return [
            Finding(
                "over-load-limit",
                "fail",
                0,
                f"{lines} lines, {size} bytes: entries past {LOAD_LINE_CAP} lines or "
                f"{LOAD_BYTE_CAP} bytes are not loaded",
            )
        ]
    if lines > LOAD_LINE_CAP * NEAR_LIMIT_SHARE or size > LOAD_BYTE_CAP * NEAR_LIMIT_SHARE:
        return [
            Finding("near-load-limit", "warn", 0, f"{lines} lines, {size} bytes of the load limit")
        ]
    return []


def added_lines(before: str, after: str) -> list[str]:
    """Lines of `after` that `before` does not account for, in order (a multiset difference)."""
    remaining = Counter(before.splitlines())
    added = []
    for line in after.splitlines():
        if remaining[line]:
            remaining[line] -= 1
        else:
            added.append(line)
    return added


def gate_messages(before: str, after: str) -> list[str]:
    """Why a write turning `before` into `after` must not land; empty when it may.

    Judges only what the write adds, plus growth past the load limit, so an
    index carrying old debt can still take a conforming new entry.
    """
    messages = [
        f"`{line[:70]}{'…' if len(line) > 70 else ''}`: {finding.detail}"
        for line in added_lines(before, after)
        for finding in _judge_line(line, 0)
    ]
    grew = len(after.encode("utf-8")) > len(before.encode("utf-8"))
    over = _size_findings(after)
    if grew and over and over[0].kind == "over-load-limit":
        messages.append(f"the index would pass the harness load limit ({over[0].detail})")
    return messages


def config_dir() -> Path:
    return Path(os.environ.get(CONFIG_DIR_VARIABLE) or Path.home() / ".claude")


def project_index(cwd: Path, config: Path) -> Path:
    """The auto-memory index of the project at `cwd`: the harness maps '/' and '.' to '-'."""
    return config / "projects" / re.sub(r"[/.]", "-", str(cwd)) / "memory" / INDEX_NAME


def all_indexes(config: Path) -> list[Path]:
    return sorted(
        [
            *config.glob(f"projects/*/memory/{INDEX_NAME}"),
            *config.glob(f"agent-memory/*/{INDEX_NAME}"),
        ]
    )


def _report(indexes: list[Path]) -> dict:
    results = {}
    for index in indexes:
        results[str(index)] = [asdict(f) for f in audit(index)]
    return results


def _render(results: dict) -> str:
    lines = []
    for index, findings in results.items():
        fails = sum(1 for f in findings if f["severity"] == "fail")
        lines.append(f"{index}: {fails} failing, {len(findings) - fails} warning")
        for f in findings:
            where = f"line {f['line']}" if f["line"] else "index"
            lines.append(f"  [{f['severity']}] {f['kind']} ({where}): {f['detail']}")
    lines.append(CONVENTION)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", type=Path, help="index files to audit")
    parser.add_argument("--all", action="store_true", help="every index in the config dir")
    parser.add_argument("--json", action="store_true", help="emit findings as JSON")
    args = parser.parse_args(argv)

    if args.all:
        indexes = all_indexes(config_dir())
    elif args.paths:
        indexes = args.paths
    else:
        indexes = [project_index(Path.cwd(), config_dir())]
    try:
        results = _report(indexes)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(results, indent=2) if args.json else _render(results))
    failing = any(f["severity"] == "fail" for findings in results.values() for f in findings)
    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main())
