"""Cost collector -- read pass: source discovery, provenance classification, dedup.

This module reads the observability write-ahead log (`.ai-state/observations.jsonl`
and its `.1` rotation archive) plus the committed per-session summary rollup
across the main checkout and every sibling worktree, classifies each
`agent_stop` row by how honestly its token usage was attributed, and
de-duplicates the honest population by `agent_id`. The aggregate pass (tier
join, per-pipeline/per-tier/per-agent-type tables, the provenance guard, and
the `Collector` subclass itself) is not part of this module yet.

Four-way honesty partition (see `_classify` below)
---------------------------------------------------
An `agent_stop` row's token fields mean different things depending on when it
was written. Before a fix to the write-ahead hook, `tokens_in`/`tokens_out`/
`cache_read`/`cache_create` held the *parent session's* cumulative usage --
not the reporting agent's own. After the fix, a `usage_source` key marks which
transcript the numbers came from. Rows written before the fix simply lack the
key entirely -- so the honest population is identified by presence of
`usage_source == "subagent-transcript"`, and the partition between "old,
unmarked" rows and "new, but every field degraded to null" rows is made by
whether the row carries any token field at all, never by the value of a
token field itself.

Source discovery (see `discover_sources` below)
-------------------------------------------------
A `session_id` is not scoped to one checkout -- the same session can produce
different committed summaries in different worktrees -- so the corpus is the
union of every checkout's own write-ahead log: the checkout this collector
runs from, the main checkout (resolved via `git rev-parse
--path-format=absolute --git-common-dir`), and every sibling worktree under
the main checkout's `.claude/worktrees/` directory. Enumerating the same set
of checkouts regardless of which one the collector is invoked from is what
gives two runs -- one from a worktree, one from the main checkout -- an
identical source set.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path

__all__ = [
    "AttributedRow",
    "Provenance",
    "SourceRef",
    "dedup_attributed_rows",
    "discover_sources",
    "read_agent_stop_rows",
]

# ---------------------------------------------------------------------------
# Tunables and named constants.
# ---------------------------------------------------------------------------

# Mirrors git_collector.py's own subprocess-timeout pattern: a single, bounded
# `git rev-parse` call must never hang this collector.
_GIT_SUBPROCESS_TIMEOUT_SECONDS: float = 10.0

_WAL_FILENAME = "observations.jsonl"
_WAL_ARCHIVE_FILENAME = "observations.jsonl.1"
_SUMMARY_FILENAME = "observations_summary.jsonl"

# SourceRef.kind values -- named here so discover_sources never repeats a
# bare string literal at each of its three enumeration call sites.
_SOURCE_KIND_WAL = "wal"
_SOURCE_KIND_WAL_ARCHIVE = "wal-archive"
_SOURCE_KIND_SUMMARY = "summary"

_AGENT_STOP_EVENT_TYPE = "agent_stop"

# The two honest-provenance marker values a post-fix row can carry. A row
# lacking the `usage_source` key entirely is the pre-fix population these
# values do not apply to -- see the module docstring's honesty partition.
_USAGE_SOURCE_SUBAGENT_TRANSCRIPT = "subagent-transcript"
_USAGE_SOURCE_PARENT_TRANSCRIPT = "parent-transcript"

# The token-shaped fields whose mere presence (irrespective of value)
# distinguishes a row that at least tried to carry usage data from one that
# carries none at all.
_TOKEN_FIELDS: tuple[str, ...] = ("tokens_in", "tokens_out", "cache_read", "cache_create")


# ---------------------------------------------------------------------------
# Provenance classification -- the four-way honesty partition.
# ---------------------------------------------------------------------------


class Provenance(StrEnum):
    """The four populations an `agent_stop` row can belong to.

    A closed set, not a bare string, so every consumer of a classified row
    can exhaustively match on it rather than re-testing string equality.
    """

    ATTRIBUTED = "attributed"
    PARENT_SOURCED = "parent-sourced"
    PRE_ATTRIBUTION = "pre-attribution"
    UNPARSED = "unparsed"


def _has_any_token_field(row: dict) -> bool:
    """True when at least one token field is present and non-null."""

    return any(row.get(field) is not None for field in _TOKEN_FIELDS)


def _classify(row: dict) -> Provenance:
    """Sole entry point for the honesty partition -- see module docstring.

    Partitions first on **absence** of the `usage_source` key, never on its
    value: absence is the marker for the pre-fix population. A row that
    carries the key with a value other than the two honest markers (e.g.
    `None`, written when a post-fix row's usage extraction fully failed) has
    no honest attribution to report and is classified `UNPARSED`.
    """

    if "usage_source" not in row:
        return Provenance.PRE_ATTRIBUTION if _has_any_token_field(row) else Provenance.UNPARSED

    usage_source = row.get("usage_source")
    if usage_source == _USAGE_SOURCE_SUBAGENT_TRANSCRIPT:
        return Provenance.ATTRIBUTED
    if usage_source == _USAGE_SOURCE_PARENT_TRANSCRIPT:
        return Provenance.PARENT_SOURCED
    return Provenance.UNPARSED


# ---------------------------------------------------------------------------
# AttributedRow -- the only representation of the honest population.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AttributedRow:
    """One honestly-attributed `agent_stop` row.

    Every numeric field is coerced at construction (see
    `_attributed_from_row`) -- a downstream consumer never has to re-check
    for `None`.
    """

    agent_id: str
    session_id: str
    pipeline_slug: str
    agent_type: str
    agent_type_source: str
    model: str
    tokens_in: int
    tokens_out: int
    cache_read: int
    cache_create: int
    duration_ms: int
    timestamp: str
    source_path: str


def _coerce_numeric(value: object) -> int:
    """`None` becomes `0`; anything else is coerced to `int`.

    Coercion happens once, here, at construction -- never re-checked by a
    downstream reader of `AttributedRow`.
    """

    return 0 if value is None else int(value)  # type: ignore[arg-type]


def _attributed_from_row(row: dict, source_path: str) -> AttributedRow | None:
    """The only constructor path for `AttributedRow`.

    Returns `None` for every row that does not classify `ATTRIBUTED` --
    callers never need to classify a row themselves before calling this.
    """

    if _classify(row) is not Provenance.ATTRIBUTED:
        return None

    return AttributedRow(
        agent_id=str(row.get("agent_id", "")),
        session_id=str(row.get("session_id", "")),
        pipeline_slug=str(row.get("project", "")),
        agent_type=str(row.get("agent_type", "")),
        agent_type_source=str(row.get("agent_type_source", "")),
        model=str(row.get("model", "")),
        tokens_in=_coerce_numeric(row.get("tokens_in")),
        tokens_out=_coerce_numeric(row.get("tokens_out")),
        cache_read=_coerce_numeric(row.get("cache_read")),
        cache_create=_coerce_numeric(row.get("cache_create")),
        duration_ms=_coerce_numeric(row.get("duration_ms")),
        timestamp=str(row.get("timestamp", "")),
        source_path=source_path,
    )


# ---------------------------------------------------------------------------
# SourceRef -- one discovered WAL/archive/summary file.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceRef:
    """One file `discover_sources` found on disk.

    `lines_scanned`/`agent_stop_rows`/`attributed_rows` start at `0` here --
    discovery only locates files, it does not read them. The aggregate pass
    populates these via `dataclasses.replace` once the read pass has run.
    """

    path: str
    kind: str
    checkout: str
    mtime_iso: str
    lines_scanned: int
    agent_stop_rows: int
    attributed_rows: int


def _mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Source discovery -- the injectable git seam plus the enumeration itself.
# ---------------------------------------------------------------------------


def _resolve_main_checkout(repo_root: str) -> tuple[str | None, str | None]:
    """Resolve the main checkout's root directory via `git rev-parse`.

    `--git-common-dir` reports the shared `.git` directory every worktree of
    a repository points at; its parent directory is the main checkout's own
    root. Returns `(main_checkout, None)` on success or `(None, reason)` on
    any failure -- a bounded, injectable seam so `discover_sources`'s tests
    never shell out to real git.
    """

    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=_GIT_SUBPROCESS_TIMEOUT_SECONDS,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return None, f"git rev-parse failed: {exc!r}"

    if completed.returncode != 0:
        reason = completed.stderr.strip() or "git rev-parse exited non-zero"
        return None, reason

    common_dir = completed.stdout.strip()
    if not common_dir:
        return None, "git rev-parse returned no output"

    return str(Path(common_dir).parent), None


def discover_sources(repo_root: str) -> tuple[list[SourceRef], list[str]]:
    """Enumerate every WAL/archive/summary file across the repository's checkouts.

    Enumerates `[repo_root, main_checkout, *sibling_worktrees]` for WAL and
    archive files first, then the same checkout list for the committed
    summary file -- two full passes, not one pass interleaving kinds per
    checkout, so the discovered order is stable regardless of which checkout
    the collector runs from -- the property that lets every checkout see the
    same source set, so a report from a worktree and one from main agree.
    A file is only included when it exists; de-duplication is by resolved
    path, so a checkout that happens to equal `repo_root` (or one already
    seen under another name) contributes its files exactly once.
    """

    issues: list[str] = []
    checkout_dirs: list[Path] = [Path(repo_root)]

    main_checkout, error = _resolve_main_checkout(repo_root)
    if main_checkout is None:
        issues.append(f"worktree discovery unavailable: {error}")
    else:
        main_path = Path(main_checkout)
        checkout_dirs.append(main_path)
        worktrees_dir = main_path / ".claude" / "worktrees"
        if worktrees_dir.is_dir():
            checkout_dirs.extend(sorted(p for p in worktrees_dir.iterdir() if p.is_dir()))

    seen_paths: set[str] = set()
    sources: list[SourceRef] = []

    def _add(dir_path: Path, kind: str, filename: str) -> None:
        candidate = dir_path / ".ai-state" / filename
        if not candidate.is_file():
            return
        resolved = str(candidate.resolve())
        if resolved in seen_paths:
            return
        seen_paths.add(resolved)
        sources.append(
            SourceRef(
                path=str(candidate),
                kind=kind,
                checkout=dir_path.name,
                mtime_iso=_mtime_iso(candidate),
                lines_scanned=0,
                agent_stop_rows=0,
                attributed_rows=0,
            )
        )

    for dir_path in checkout_dirs:
        _add(dir_path, _SOURCE_KIND_WAL, _WAL_FILENAME)
        _add(dir_path, _SOURCE_KIND_WAL_ARCHIVE, _WAL_ARCHIVE_FILENAME)
    for dir_path in checkout_dirs:
        _add(dir_path, _SOURCE_KIND_SUMMARY, _SUMMARY_FILENAME)

    return sources, issues


# ---------------------------------------------------------------------------
# Streaming reader -- one source file, filtered to agent_stop rows.
# ---------------------------------------------------------------------------


def read_agent_stop_rows(path: str) -> tuple[list[dict], str | None]:
    """Stream one source file, returning its `agent_stop` rows.

    Streamed line-by-line (never `read_text()`), mirroring
    `_sum_subagent_transcript`'s discipline for a file that can grow large,
    including its rule that a malformed line is skipped, never fatal to the
    rest of the scan: the WAL is append-only and live, so a torn trailing
    line while a session runs is a normal state, not corruption of the rows
    before it. Every skip is counted into the named issue so the reader
    sees a partial file as partial. A missing or unreadable file degrades
    to zero rows with a named issue.
    """

    file_path = Path(path)
    if not file_path.is_file():
        return [], f"missing source file: {path}"

    rows: list[dict] = []
    skipped = 0
    try:
        with open(file_path, encoding="utf-8", errors="replace") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    skipped += 1
                    continue
                if isinstance(row, dict) and row.get("event_type") == _AGENT_STOP_EVENT_TYPE:
                    rows.append(row)
    except OSError as exc:
        return [], f"unreadable source {path}: {exc}"

    if skipped:
        noun = "line" if skipped == 1 else "lines"
        return rows, f"skipped {skipped} malformed {noun} in {path}"
    return rows, None


# ---------------------------------------------------------------------------
# Dedup -- last-in-file, first-across-files, by agent_id.
# ---------------------------------------------------------------------------


def dedup_attributed_rows(
    rows: Sequence[AttributedRow],
) -> tuple[list[AttributedRow], list[str]]:
    """Keep exactly one row per `agent_id`.

    Pure over an already-ordered sequence -- source order, then file order
    within a source, is the sequence's own order; no separate ordering
    parameter is needed. Within one file, a later row for the same
    `agent_id` replaces the earlier one (last-in-file wins), even when the
    two rows carry different payloads -- a same-`agent_id` repeat is
    assumed to be a re-write of the same event, not two independent
    contributions. Across files, the first file to have contributed a row
    for an `agent_id` keeps it; a later file's row for the same id is
    recorded in `duplicate_agent_ids`, never merged or summed.
    """

    winners: dict[str, AttributedRow] = {}
    first_seen_order: list[str] = []
    duplicate_agent_ids: list[str] = []
    already_recorded: set[str] = set()

    for row in rows:
        existing = winners.get(row.agent_id)
        if existing is None:
            winners[row.agent_id] = row
            first_seen_order.append(row.agent_id)
            continue
        if existing.source_path == row.source_path:
            winners[row.agent_id] = row  # last-in-file wins
            continue
        if row.agent_id not in already_recorded:
            duplicate_agent_ids.append(row.agent_id)
            already_recorded.add(row.agent_id)
        # Cross-file repeat: the earlier file's row already in `winners` stays.

    deduped = [winners[agent_id] for agent_id in first_seen_order]
    return deduped, duplicate_agent_ids
