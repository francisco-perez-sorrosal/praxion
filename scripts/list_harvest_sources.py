#!/usr/bin/env python3
"""Enumerate a skill-genesis harvest queue and plan its batches.

`/skill-genesis` harvests one pipeline directory per spawn: the agent reads
`.ai-work/<slug>/LEARNINGS.md`, `VERIFICATION_REPORT.md` and any
`CONSULT_*.md` fragment. Finished pipelines are parked under
`.ai-work/_harvest/<slug>/` (sometimes one level deeper, when a worktree's
whole `.ai-work/` tree was copied in) so their worktrees can be removed. For
eleven days that queue had no reader: the command's pre-flight globbed
`.ai-work/*/LEARNINGS.md` one level deep and the agent contract named a
single slug, so every queued directory was invisible to the harvest.

This script is the pre-flight for queue mode. It answers three questions
the command needs before spawning anything:

1. **Which directories are sources?** Any directory at depth <= `--max-depth`
   under the queue that holds at least one harvestable file. Loose files at
   the queue root (handoffs) and directories holding only pipeline plumbing
   (`WIP.md`, `TASK_BRIEF.md`) are not sources.
2. **Which sources were already promoted?** `prior_report` is true when an
   existing `SKILL_GENESIS_REPORT_*.md` cites the source's path or its
   `.ai-work/<slug>/` form; `memory` is true when a file in the harness memory
   directory names the slug. Both are cheap textual markers with declared
   limits: they say "something was captured", never "everything was". When no
   memory directory is given the marker is withheld (`null`), not reported as
   false.
3. **How many spawns?** Sources are packed greedily, in path order, under
   `--cap` bytes of source text per batch. A single source over the cap is a
   batch of its own, flagged `oversize`, so the agent can sample it by section
   rather than read it whole.

Stdlib-only, so the ambient interpreter can run it. Exit codes: ``0`` sources
found, ``2`` no sources (missing or empty queue) or a script error.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from _repo_root import resolve_repo_root

__all__ = ["Batch", "Source", "enumerate_sources", "mark_promoted", "plan_batches", "main"]

_LOG = logging.getLogger("list_harvest_sources")

_DEFAULT_SOURCES = Path(".ai-work") / "_harvest"
_DEFAULT_REPORTS = Path(".ai-state") / "skill_genesis_reports"
_REPORT_GLOB = "SKILL_GENESIS_REPORT_*.md"
_DEFAULT_CAP_BYTES = 200_000
_DEFAULT_MAX_DEPTH = 2
_EXACT_NAMES = frozenset({"LEARNINGS.md", "VERIFICATION_REPORT.md"})
_PREFIX_NAMES = ("CONSULT_",)


def _is_harvestable(name: str) -> bool:
    return name in _EXACT_NAMES or (name.startswith(_PREFIX_NAMES) and name.endswith(".md"))


@dataclass
class Source:
    """One harvestable directory under the queue."""

    rel: str
    slug: str
    path: Path
    files: list[Path]
    total_bytes: int
    prior_report: bool | None = None
    memory: bool | None = None

    def to_json(self) -> dict[str, object]:
        d = asdict(self)
        d["path"] = str(self.path)
        d["files"] = [{"name": f.name, "bytes": f.stat().st_size} for f in self.files]
        return d


@dataclass
class Batch:
    """A group of sources one agent spawn reads."""

    index: int
    sources: list[Source] = field(default_factory=list)
    oversize: bool = False

    @property
    def total_bytes(self) -> int:
        return sum(s.total_bytes for s in self.sources)

    def to_json(self) -> dict[str, object]:
        return {
            "index": self.index,
            "total_bytes": self.total_bytes,
            "oversize": self.oversize,
            "sources": [s.rel for s in self.sources],
        }


def enumerate_sources(queue: Path, *, max_depth: int = _DEFAULT_MAX_DEPTH) -> list[Source]:
    """Every directory at depth <= `max_depth` under `queue` holding a harvestable file, in path order."""
    if not queue.is_dir():
        return []
    found: list[Source] = []
    for d in sorted(p for p in queue.rglob("*") if p.is_dir()):
        depth = len(d.relative_to(queue).parts)
        if depth > max_depth:
            continue
        files = sorted(f for f in d.iterdir() if f.is_file() and _is_harvestable(f.name))
        if not files:
            continue
        rel = d.relative_to(queue).as_posix()
        found.append(
            Source(
                rel=rel,
                slug=d.name,
                path=d,
                files=files,
                total_bytes=sum(f.stat().st_size for f in files),
            )
        )
    return found


def _read_all(directory: Path | None, pattern: str) -> str:
    if directory is None or not directory.is_dir():
        return ""
    return "\n".join(
        p.read_text(errors="replace") for p in sorted(directory.glob(pattern)) if p.is_file()
    )


def mark_promoted(
    sources: list[Source], *, reports_dir: Path | None, memory_dir: Path | None
) -> list[Source]:
    """Set `prior_report` / `memory` on each source; `memory` stays None without a memory dir."""
    reports_text = _read_all(reports_dir, _REPORT_GLOB)
    memory_text = _read_all(memory_dir, "*.md") if memory_dir is not None else None
    for s in sources:
        cited = f"/{s.rel}/" in reports_text or f"/{s.slug}/" in reports_text
        s.prior_report = cited
        s.memory = None if memory_text is None else (s.slug in memory_text)
    return sources


def plan_batches(sources: list[Source], *, cap_bytes: int = _DEFAULT_CAP_BYTES) -> list[Batch]:
    """Greedy packing in source order; an over-cap source is its own flagged batch."""
    batches: list[Batch] = []
    current: Batch | None = None
    for s in sources:
        if s.total_bytes > cap_bytes:
            batches.append(Batch(index=len(batches) + 1, sources=[s], oversize=True))
            current = None
            continue
        if current is None or current.total_bytes + s.total_bytes > cap_bytes:
            current = Batch(index=len(batches) + 1)
            batches.append(current)
        current.sources.append(s)
    return batches


def _marker(value: bool | None) -> str:
    return "n/a" if value is None else ("yes" if value else "no")


def _render_text(queue: Path, sources: list[Source], batches: list[Batch], cap_bytes: int) -> str:
    lines = [f"harvest queue: {queue}  ({len(sources)} sources, cap {cap_bytes:,} bytes/batch)", ""]
    lines.append(f"{'source':<48} {'bytes':>9}  prior-report  memory  files")
    for s in sources:
        names = ", ".join(f.name for f in s.files)
        lines.append(
            f"{s.rel:<48} {s.total_bytes:>9,}  {_marker(s.prior_report):<12}  {_marker(s.memory):<6}  {names}"
        )
    lines.append("")
    for b in batches:
        tag = "  [oversize: sample by section]" if b.oversize else ""
        lines.append(f"Batch {b.index}: {b.total_bytes:,} bytes, {len(b.sources)} source(s){tag}")
        lines.extend(f"  - {s.rel}" for s in b.sources)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument(
        "--sources", default=None, help=f"queue directory (default: {_DEFAULT_SOURCES})"
    )
    parser.add_argument(
        "--cap", type=int, default=_DEFAULT_CAP_BYTES, help="max source bytes per batch"
    )
    parser.add_argument(
        "--max-depth", type=int, default=_DEFAULT_MAX_DEPTH, help="how deep to look for sources"
    )
    parser.add_argument(
        "--reports-dir", default=None, help=f"prior reports (default: {_DEFAULT_REPORTS})"
    )
    parser.add_argument(
        "--memory-dir", default=None, help="harness memory directory; omit to withhold the marker"
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--repo-root", default=None, help="repository root (defaults to git root)")
    parser.add_argument("--verbose", action="store_true", help="enable DEBUG logging")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING, format="%(message)s"
    )

    try:
        repo_root = resolve_repo_root(args.repo_root, script_dir=Path(__file__).resolve().parent)
        queue = Path(args.sources) if args.sources else repo_root / _DEFAULT_SOURCES
        reports_dir = Path(args.reports_dir) if args.reports_dir else repo_root / _DEFAULT_REPORTS
        memory_dir = Path(args.memory_dir) if args.memory_dir else None

        sources = enumerate_sources(queue, max_depth=args.max_depth)
        if not sources:
            print(f"no harvest sources under {queue}", file=sys.stderr)
            return 2
        mark_promoted(sources, reports_dir=reports_dir, memory_dir=memory_dir)
        batches = plan_batches(sources, cap_bytes=args.cap)
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        _LOG.error("list_harvest_sources failed: %s", exc)
        return 2

    if args.json:
        payload = {
            "sources_dir": str(queue),
            "cap_bytes": args.cap,
            "sources": [s.to_json() for s in sources],
            "batches": [b.to_json() for b in batches],
        }
        print(json.dumps(payload, indent=2))
    else:
        print(_render_text(queue, sources, batches, args.cap))
    return 0


if __name__ == "__main__":
    sys.exit(main())
