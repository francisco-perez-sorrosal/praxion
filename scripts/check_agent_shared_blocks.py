#!/usr/bin/env python3
"""Hold the shared prose blocks replicated across agent definitions byte-identical.

One paragraph -- the task-slug scoping statement -- is inlined into fifteen
files under ``agents/``. It cannot be extracted: agents inherit neither rules
nor ``CLAUDE.md`` content, and ``agent-crafting`` forbids runtime reference
files for plugin-distributed agents (a sub-agent's ``Read`` resolves against
the *consumer's* working directory, not the plugin cache, so the read fails
silently and the agent runs on without the missing content). So the block stays
physically inline in all fifteen files, and the only available remedy is the
other one ``rules/swe/gate-liveness.md`` names for its two-textual-sites
anti-pattern: **a single source of truth, with every site checked against it**.

It had already forked. Four textually distinct tails were in circulation --
``for all document reads and writes.``, ``for reads.``, no tail at all (the
sentence simply stopped after the path), and the current one -- each arrived at
by a separate edit to a separate file, none visible from any other. Nothing
detected that, because nothing was looking.

**Where the source of truth lives, and why here.** Not in
``claude/canonical-blocks/``. That directory looks like the natural home and is
not: its files are ``## Heading``-shaped sections shipped into *managed
projects'* ``CLAUDE.md``, embedded into consumer commands behind
``<!-- canonical-source: ... -->`` fences, and governed end-to-end by the
``BLOCKS`` registry in ``sync_canonical_blocks.py`` -- which
``check_architecture_projection.py`` parses, ``canonical_block_identity``
subsets into ``REFRESHABLE_SLUGS``, and ``refresh_claude_blocks.py`` consumes at
runtime. Every one of those keys off the registry, never off a directory
listing, so a file dropped in there without a registry entry is a stowaway that
no mechanism governing the directory can see. Registering it properly is not
available either: it would mean fence anchors in all fifteen agent files, and
this block is a mid-paragraph *sentence* with per-agent lead-in clauses, not a
fenced section. Different shape, different destination, different lifecycle.

So the canonical text is a constant in this file -- the one place that reads it
-- and ``--print-canonical`` makes it obtainable rather than merely asserted, so
an author changing the block can paste the exact bytes into all fifteen sites
instead of retyping them into a sixteenth variant.

**Scope fidelity.** Documented scope and computed scope are the same glob:
``agents/*.md``. This gate answers *"every site that carries this block carries
it identically"* -- not *"every agent that should carry it does"*. The latter
needs a hardcoded roster of which agents are in scope, and a hardcoded roster is
itself the drift vector this gate exists to close. Carriers are detected, never
enumerated.

**Lead-ins are not drift.** Five agents open the line with their own clause
(``Determine what you have to work with.``, ``Before gathering information,
clarify what needs to be researched.``) and one continues past it (``Read these
at start:``). Those are legitimate per-agent context. The comparison unit is
therefore the canonical *sentence* anchored at ``The **task slug**``, not the
whole line: anything before the anchor and anything after the sentence is free.
A gate that reported correct work as drift would teach its reader to skip it.

Two finding kinds:

``drifted``
    The anchor is present and the bytes following it are not the canonical
    sentence. Carries the first differing column and a unified diff.

``anchor-missing``
    The line is unmistakably this block (it carries one of the tells) but the
    anchor is gone -- someone dropped the bold, or reworded the head. Without
    this kind, head drift would make a line *undetectable* and the gate would
    report a false all-clear on it.

Stdlib-only, deliberately: this gate is registered with ``language: system`` and
is named in prose, so a third-party import would make it a finding of
``check_gate_liveness.py --check ambient-import``.

Exit codes: 0 clean, 1 findings, 2 script error.

Usage:
    python3 scripts/check_agent_shared_blocks.py
    python3 scripts/check_agent_shared_blocks.py --json
    python3 scripts/check_agent_shared_blocks.py --print-canonical
    python3 scripts/check_agent_shared_blocks.py --repo-root PATH
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from _repo_root import resolve_repo_root

SCRIPT_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class SharedBlock:
    """One prose block replicated verbatim across agent definitions.

    ``canonical`` is the authority. ``anchor`` is the prefix of ``canonical``
    at which the comparison window opens -- everything to its left on the line
    is a per-agent lead-in and is not compared. ``tells`` are the loose
    fragments that mark a line as *claiming to be* this block; they exist so
    that drift in the anchor itself surfaces as a finding rather than as
    silence.
    """

    slug: str
    canonical: str
    anchor: str
    tells: tuple[str, ...]
    corroborators: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.canonical.startswith(self.anchor):
            raise ValueError(f"{self.slug}: anchor is not a prefix of the canonical text")


# The canonical text. THIS IS THE SOURCE OF TRUTH for the fifteen inline copies
# under agents/. Changing the block means changing this constant and every site
# it governs in the same commit -- run `--print-canonical` to get the bytes.
_TASK_SLUG_SCOPING = (
    "The **task slug** (provided in your prompt as `Task slug: <slug>`) scopes all "
    "`.ai-work/` paths to `.ai-work/<task-slug>/`. Use this path for all reads and writes."
)

SHARED_BLOCKS: tuple[SharedBlock, ...] = (
    SharedBlock(
        slug="task-slug-scoping",
        canonical=_TASK_SLUG_SCOPING,
        anchor="The **task slug**",
        # `provided in your prompt as` occurs nowhere else in the repository, so
        # it identifies the block on its own. The bold form is weaker -- a
        # command and an analysis doc bold the same words in ordinary prose --
        # so it is paired with `.ai-work/`, which those two lines lack. Either
        # tell alone is enough to make a line a candidate: each covers for drift
        # in the other.
        tells=("provided in your prompt as",),
        corroborators=("**task slug**", ".ai-work/"),
    ),
)

# The surface the block is replicated across. A glob, not a roster: an agent
# that gains or loses the block is picked up without editing this file.
SCAN_GLOB = "agents/*.md"


@dataclass(frozen=True)
class Finding:
    """One site whose copy of a shared block does not match the source of truth."""

    kind: str
    block: str
    file: str
    line: int
    detail: str
    diff: list[str] = field(default_factory=list)


def _is_candidate(line: str, block: SharedBlock) -> bool:
    """True when `line` claims to be `block`, however far it has drifted."""
    if any(tell in line for tell in block.tells):
        return True
    return (
        all(fragment in line for fragment in block.corroborators) if block.corroborators else False
    )


def _first_divergence(observed: str, canonical: str) -> int:
    """1-based column of the first differing character between the two strings."""
    # strict=False is the point: the two strings routinely differ in length
    # (a truncated tail is one of the historical variants), and the common
    # prefix is exactly what this walks.
    for index, (left, right) in enumerate(zip(observed, canonical, strict=False)):
        if left != right:
            return index + 1
    return min(len(observed), len(canonical)) + 1


def _inspect_line(line: str, lineno: int, rel: str, block: SharedBlock) -> Finding | None:
    """Compare one candidate line's copy of `block` against the canonical text."""
    start = line.find(block.anchor)
    if start < 0:
        return Finding(
            kind="anchor-missing",
            block=block.slug,
            file=rel,
            line=lineno,
            detail=(
                f"line carries this block but not its anchor {block.anchor!r}; "
                "the head of the sentence has drifted and no byte-comparison is possible"
            ),
            diff=list(
                difflib.unified_diff(
                    [block.canonical], [line.strip()], "canonical", f"{rel}:{lineno}", lineterm=""
                )
            ),
        )

    observed = line[start:]
    if observed[: len(block.canonical)] == block.canonical:
        return None

    column = _first_divergence(observed, block.canonical)
    return Finding(
        kind="drifted",
        block=block.slug,
        file=rel,
        line=lineno,
        detail=f"diverges from the canonical text at column {column} of the sentence",
        diff=list(
            difflib.unified_diff(
                [block.canonical], [observed], "canonical", f"{rel}:{lineno}", lineterm=""
            )
        ),
    )


def check_agent_shared_blocks(root: Path) -> dict[str, Any]:
    """Verify every inline copy of every shared block matches its source of truth."""
    targets = sorted(p for p in root.glob(SCAN_GLOB) if p.is_file())
    findings: list[Finding] = []
    carriers: dict[str, list[str]] = {block.slug: [] for block in SHARED_BLOCKS}

    for path in targets:
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            findings.append(Finding("unreadable", "-", rel, 1, str(exc)))
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for block in SHARED_BLOCKS:
                if not _is_candidate(line, block):
                    continue
                carriers[block.slug].append(rel)
                finding = _inspect_line(line, lineno, rel, block)
                if finding is not None:
                    findings.append(finding)

    return {
        "scanned": len(targets),
        "blocks": {
            block.slug: {
                "carriers": len(carriers[block.slug]),
                "files": sorted(set(carriers[block.slug])),
            }
            for block in SHARED_BLOCKS
        },
        "findings": [asdict(f) for f in findings],
    }


def _render_human(report: dict[str, Any]) -> str:
    lines = [f"Scanned {report['scanned']} agent definition(s) under {SCAN_GLOB}."]
    for slug, info in report["blocks"].items():
        lines.append(f"  {slug}: {info['carriers']} inline copy/copies")
    if not report["findings"]:
        lines.append("  every inline copy matches its canonical source of truth")
        return "\n".join(lines)

    lines.append("")
    for finding in report["findings"]:
        lines.append(
            f"  {finding['kind']}: {finding['file']}:{finding['line']} [{finding['block']}]"
        )
        lines.append(f"    {finding['detail']}")
        for diff_line in finding["diff"]:
            lines.append(f"      {diff_line.rstrip()}")
    lines.append(
        f"\n{len(report['findings'])} inline copy/copies drifted from the canonical text. "
        f"Run `{Path(__file__).name} --print-canonical` for the exact bytes."
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify prose blocks replicated across agent definitions stay byte-identical."
    )
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    parser.add_argument(
        "--print-canonical",
        metavar="SLUG",
        nargs="?",
        const=SHARED_BLOCKS[0].slug,
        help="print a block's canonical text and exit (default: %(default)s)",
        default=None,
    )
    parser.add_argument("--repo-root", help="repository root (defaults to git discovery)")
    args = parser.parse_args(argv)

    if args.print_canonical is not None:
        matches = [b for b in SHARED_BLOCKS if b.slug == args.print_canonical]
        if not matches:
            known = ", ".join(b.slug for b in SHARED_BLOCKS)
            print(
                f"error: unknown block {args.print_canonical!r}; known blocks: {known}",
                file=sys.stderr,
            )
            return 2
        print(matches[0].canonical)
        return 0

    try:
        report = check_agent_shared_blocks(resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR))
    except OSError as exc:  # pragma: no cover - defensive
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(report, indent=2) if args.json else _render_human(report))
    return 1 if report["findings"] else 0


if __name__ == "__main__":
    sys.exit(main())
