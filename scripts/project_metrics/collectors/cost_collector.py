"""Cost collector -- read pass plus aggregate pass.

This module reads the observability write-ahead log (`.ai-state/observations.jsonl`
and its `.1` rotation archive) plus the committed per-session summary rollup
across the main checkout and every sibling worktree, classifies each
`agent_stop` row by how honestly its token usage was attributed, and
de-duplicates the honest population by `agent_id` (the read pass). It then
joins each pipeline to a calibration tier, folds the honest rows into one
bucket list that every per-pipeline/per-tier/per-agent-type table projects
from, re-derives its own totals before publishing them, and exposes the
`CostCollector` class the runner registers (the aggregate pass).

Guard independence (see `_audit_totals` below)
------------------------------------------------
The aggregate pass re-derives its own provenance counts through
`_partition_provenance` -- the same classification logic `_classify` wraps --
called directly, never through the `_classify` name itself. `_classify` is
the single patchable entry point the read pass uses to build the rows that
actually feed the rendered tables; `_partition_provenance` is what the
guard's independent census reads instead. In ordinary operation the two
agree on every row (one simply wraps the other), so the guard is silent.
Only when something replaces the `_classify` symbol specifically -- the
attack the guard exists to catch -- do the two counts diverge, because the
census path never went through the replaced symbol to begin with.

Four-way honesty partition (see `_classify` below)
---------------------------------------------------
An `agent_stop` row's token fields mean different things depending on when it
was written. Before a fix to the write-ahead hook, `tokens_in`/`tokens_out`/
`cache_read`/`cache_create` held the *parent session's* cumulative usage --
not the reporting agent's own. After the fix, a `usage_source` key marks which
transcript the numbers came from. Rows written before the fix simply lack the
key entirely -- so the honest population is identified by presence of
`usage_source == "subagent-transcript"` together with at least one readable
token field, and the partition between "old, unmarked" rows and "new, but
every field degraded to null" rows is made by whether the row carries any
token field at all. A token field that is present but unreadable (a string,
an infinity) quarantines its row as `unparsed` on both the read path and the
census, so an understated total can never be published as an honest one.

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

import dataclasses
import json
import re
import statistics
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, TypeVar

from scripts.project_metrics.collectors.base import (
    Available,
    CollectionContext,
    Collector,
    CollectorResult,
    NotApplicable,
    ResolutionEnv,
    ResolutionResult,
)

__all__ = [
    "AttributedRow",
    "CostCollector",
    "Coverage",
    "PipelineBucket",
    "Provenance",
    "SourceRef",
    "TierAmbiguous",
    "TierResolved",
    "TierUnknown",
    "build_pipeline_buckets",
    "compute_standard_vs_lightweight_cell",
    "dedup_attributed_rows",
    "discover_sources",
    "parse_calibration_log",
    "read_agent_stop_rows",
    "resolve_tier",
    "summary_row_is_rollup_unattributed",
    "summary_row_slug",
    "unresolved_agent_type_share",
]

_T = TypeVar("_T")

# ---------------------------------------------------------------------------
# Tunables and named constants.
# ---------------------------------------------------------------------------

# Mirrors git_collector.py's own subprocess-timeout pattern: a single, bounded
# `git rev-parse` call must never hang this collector.
_GIT_SUBPROCESS_TIMEOUT_SECONDS: float = 10.0

_WAL_FILENAME = "observations.jsonl"
_WAL_ARCHIVE_FILENAME = "observations.jsonl.1"
_SUMMARY_FILENAME = "observations_summary.jsonl"
_CALIBRATION_LOG_FILENAME = "calibration_log.md"

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

# The token-shaped fields whose presence distinguishes a row that at least
# tried to carry usage data from one that carries none at all -- and whose
# readability (int-coercible) decides whether the row can enter a total.
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


def _is_int_coercible(value: object) -> bool:
    try:
        int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return False
    return True


def _has_any_token_field(row: dict) -> bool:
    """True when at least one token field is present and non-null."""

    return any(row.get(field) is not None for field in _TOKEN_FIELDS)


def _has_unreadable_token_field(row: dict) -> bool:
    """True when a present token field holds a value no total can absorb
    (`"n/a"`, `Infinity`, a list) -- such a row is quarantined by name
    rather than entering a total understated."""

    return any(
        row.get(field) is not None and not _is_int_coercible(row.get(field))
        for field in _TOKEN_FIELDS
    )


def _classify(row: dict) -> Provenance:
    """Sole entry point the read pass uses to build attributed rows.

    A thin, patchable wrapper over `_partition_provenance` -- deliberately
    kept as a separate name (rather than inlining the partition here) so the
    aggregate pass's guard can call the partition logic directly, bypassing
    this exact symbol. See the module docstring's "Guard independence" note.
    """

    return _partition_provenance(row)


def _partition_provenance(row: dict) -> Provenance:
    """The four-way honesty partition -- see the module docstring.

    Partitions first on **absence** of the `usage_source` key, never on its
    value: absence is the marker for the pre-fix population. A row that
    carries the key with a value other than the two honest markers (e.g.
    `None`, written when a post-fix row's usage extraction fully failed) has
    no honest attribution to report and is classified `UNPARSED` -- as does
    a row carrying the honest marker over four null usage fields, which has
    nothing to attribute and must not enter a total as a zero-token row, and
    a row whose token field holds a value no total can absorb, which would
    otherwise enter a total understated with nothing in the report saying so.
    """

    readable = _has_any_token_field(row) and not _has_unreadable_token_field(row)
    if "usage_source" not in row:
        return Provenance.PRE_ATTRIBUTION if readable else Provenance.UNPARSED

    usage_source = row.get("usage_source")
    if usage_source == _USAGE_SOURCE_SUBAGENT_TRANSCRIPT:
        return Provenance.ATTRIBUTED if readable else Provenance.UNPARSED
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
    """`None` and anything not int-coercible become `0`.

    Coercion happens once, here, at construction -- never re-checked by a
    downstream reader of `AttributedRow`. Token fields were screened by the
    partition (an unreadable one quarantines its row), so the fallback is
    reached only for a non-token field such as `duration_ms`; it never
    raises out of the read pass and loses every other source.
    """

    if value is None or not _is_int_coercible(value):
        return 0
    return int(value)  # type: ignore[arg-type]


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
    # Resolved up front so a published `SourceRef` is always absolute with a
    # named checkout, whatever shape the caller handed in (the runner's own
    # context carries the literal ".").
    checkout_dirs: list[Path] = [Path(repo_root).resolve()]

    main_checkout, error = _resolve_main_checkout(repo_root)
    if main_checkout is None:
        issues.append(f"worktree discovery unavailable: {error}")
    else:
        main_path = Path(main_checkout).resolve()
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
                path=resolved,
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
# Streaming reader -- one source file at a time, line-by-line.
# ---------------------------------------------------------------------------


def _stream_jsonl(path: str) -> tuple[list[dict], int, str | None]:
    """Stream one JSONL file, returning parsed object rows, a malformed-line
    skip count, and a fatal reason when the file itself cannot be read.

    Shared by `read_agent_stop_rows` (which further filters to `agent_stop`
    events) and `_read_summary_rows` (which does not filter at all) -- both
    need the identical missing/malformed-file degradation, streamed
    line-by-line (never `read_text()`) for a file that can grow large. A
    malformed line is skipped, never fatal to the rest of the scan: the WAL
    is append-only and live, so a torn trailing line while a session runs is
    a normal state, not corruption of the rows before it.
    """

    file_path = Path(path)
    if not file_path.is_file():
        return [], 0, f"missing source file: {path}"

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
                if isinstance(row, dict):
                    rows.append(row)
    except OSError as exc:
        return [], 0, f"unreadable source {path}: {exc}"

    return rows, skipped, None


def _skip_issue(skipped: int, path: str) -> str:
    noun = "line" if skipped == 1 else "lines"
    return f"skipped {skipped} malformed {noun} in {path}"


def read_agent_stop_rows(path: str) -> tuple[list[dict], str | None]:
    """Stream one source file, returning its `agent_stop` rows.

    Every skip is counted into the named issue so the reader sees a partial
    file as partial. A missing or unreadable file degrades to zero rows with
    a named issue.
    """

    rows, skipped, fatal = _stream_jsonl(path)
    if fatal is not None:
        return [], fatal
    agent_stop_rows = [row for row in rows if row.get("event_type") == _AGENT_STOP_EVENT_TYPE]
    if skipped:
        return agent_stop_rows, _skip_issue(skipped, path)
    return agent_stop_rows, None


def _read_summary_rows(path: str) -> tuple[list[dict], str | None]:
    """Stream one committed session-summary file, returning every row.

    Unlike `read_agent_stop_rows`, no `event_type` filter applies -- a
    summary row is a different shape entirely (one row per session, not per
    agent-stop event). Degradation rules are otherwise identical.
    """

    rows, skipped, fatal = _stream_jsonl(path)
    if fatal is not None:
        return [], fatal
    if skipped:
        return rows, _skip_issue(skipped, path)
    return rows, None


# ---------------------------------------------------------------------------
# Dedup -- last-in-file, first-across-files, by agent_id.
# ---------------------------------------------------------------------------


def _dedup_by_agent_id(
    items: Sequence[_T],
    agent_id_of: Callable[[_T], str],
    source_path_of: Callable[[_T], str],
) -> tuple[list[_T], list[str], int]:
    """Shared last-in-file/first-across-file dedup core.

    Generalised over an item-shape-agnostic pair of accessors so both the
    read pass's `AttributedRow` dedup and the aggregate pass's independent,
    provenance-agnostic dedup (see `_audit_totals`'s guard) apply the exact
    same rule -- a genuine divergence between the two is then only possible
    when the classification feeding them differs, never when the dedup
    algorithm itself does.

    Returns `(deduped, duplicate_agent_ids, dropped_count)`. `dropped_count`
    is this call's own arithmetic (`len(items) - len(deduped)`), returned
    alongside the deduped list rather than recomputed by the caller from
    before/after lengths -- a caller-side recompute would just re-measure
    whatever this function actually returned and could never expose a bug
    in the function itself; the aggregate pass's guard needs a figure that
    is genuinely this function's own claim, not a tautological echo of it.
    """

    winners: dict[str, _T] = {}
    first_seen_order: list[str] = []
    duplicate_agent_ids: list[str] = []
    already_recorded: set[str] = set()

    for item in items:
        agent_id = agent_id_of(item)
        existing = winners.get(agent_id)
        if existing is None:
            winners[agent_id] = item
            first_seen_order.append(agent_id)
            continue
        if source_path_of(existing) == source_path_of(item):
            winners[agent_id] = item  # last-in-file wins
            continue
        if agent_id not in already_recorded:
            duplicate_agent_ids.append(agent_id)
            already_recorded.add(agent_id)
        # Cross-file repeat: the earlier file's item already in `winners` stays.

    deduped = [winners[agent_id] for agent_id in first_seen_order]
    return deduped, duplicate_agent_ids, len(items) - len(deduped)


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

    deduped, duplicate_agent_ids, _dropped_count = _dedup_by_agent_id(
        rows, agent_id_of=lambda row: row.agent_id, source_path_of=lambda row: row.source_path
    )
    return deduped, duplicate_agent_ids


# ---------------------------------------------------------------------------
# Tier join -- resolving a pipeline slug to a calibration-log tier.
# ---------------------------------------------------------------------------

# The calibration log is a pipe-table; columns are positional, matching
# `scripts/state_ledger_schema.py`'s own registration of this file.
_CALIBRATION_TASK_COLUMN = 1
_CALIBRATION_ACTUAL_TIER_COLUMN = 4
_CALIBRATION_MIN_COLUMNS = 5

_TIER_TOKEN_PATTERN = re.compile(r"[A-Za-z]+")
_KNOWN_TIERS = frozenset({"Direct", "Lightweight", "Standard", "Full", "Spike"})


@dataclass(frozen=True)
class TierResolved:
    """One row, or several agreeing rows, name the same tier."""

    tier: str
    rows: int


@dataclass(frozen=True)
class TierAmbiguous:
    """Several calibration rows for the same slug disagree on tier.

    A silent first-wins pick would fabricate a tier -- every disagreeing
    tier is listed, never just the first one seen.
    """

    tiers: list[str]
    rows: int


@dataclass(frozen=True)
class TierUnknown:
    """No calibration row joins this slug, or its tier cell does not parse."""

    reason: str


def _calibration_row_cells(line: str) -> list[str] | None:
    """Split one pipe-table line into stripped cells, or `None` when the
    line is not a table row at all."""

    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    return [cell.strip() for cell in stripped.strip("|").split("|")]


def parse_calibration_log(path: str) -> dict[str, list[str]]:
    """Build the slug -> tier-tokens index from `.ai-state/calibration_log.md`.

    The slug is the Task cell's first whitespace-delimited token (the only
    rule that holds uniformly across every observed row shape -- a
    sub-step qualifier after `/` or free prose after an em-dash both leave
    the pipeline slug as the leading token). The tier is the Actual Tier
    cell's leading alphabetic run, lower-cased comparisons never needed
    since the log itself capitalizes tier names consistently.
    """

    index: dict[str, list[str]] = {}
    # `errors="replace"` matches the WAL reader and the producing hook: one
    # bad byte degrades one cell, never the whole index.
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        cells = _calibration_row_cells(line)
        if cells is None or len(cells) < _CALIBRATION_MIN_COLUMNS:
            continue
        task_cell = cells[_CALIBRATION_TASK_COLUMN]
        if task_cell.lower() == "task" or set(task_cell) <= {"-"}:
            continue  # header or separator row
        tokens = task_cell.split()
        if not tokens:
            continue
        slug = tokens[0]
        match = _TIER_TOKEN_PATTERN.match(cells[_CALIBRATION_ACTUAL_TIER_COLUMN])
        if match is None:
            continue
        index.setdefault(slug, []).append(match.group(0))
    return index


def resolve_tier(
    slug: str, tier_index: dict[str, list[str]]
) -> TierResolved | TierAmbiguous | TierUnknown:
    """Join `slug` to a tier -- never a function, so three outcomes exist."""

    raw_tiers = tier_index.get(slug)
    if not raw_tiers:
        return TierUnknown(reason="no-calibration-row")

    known_tiers = [tier for tier in raw_tiers if tier in _KNOWN_TIERS]
    if not known_tiers:
        return TierUnknown(reason="unparsable-tier-cell")

    unique_tiers = sorted(set(known_tiers))
    if len(unique_tiers) == 1:
        return TierResolved(tier=unique_tiers[0], rows=len(known_tiers))
    return TierAmbiguous(tiers=unique_tiers, rows=len(known_tiers))


def _flatten_tier(resolution: TierResolved | TierAmbiguous | TierUnknown) -> tuple[str, str | None]:
    """Render a tier-join outcome as the flat `(tier, tier_reason)` pair every
    downstream consumer (buckets, tables, the Standard-vs-Lightweight cell) reads instead of the
    raw union."""

    if isinstance(resolution, TierResolved):
        return resolution.tier, None
    if isinstance(resolution, TierAmbiguous):
        return "ambiguous", ", ".join(resolution.tiers)
    return "unknown", resolution.reason


# ---------------------------------------------------------------------------
# Pipeline bucket aggregation -- one bucket list, three projections.
# ---------------------------------------------------------------------------

_TOKEN_COMPONENT_KEYS: tuple[str, ...] = ("tokens_in", "tokens_out", "cache_read", "cache_create")


def _empty_token_totals() -> dict[str, int]:
    totals = dict.fromkeys(_TOKEN_COMPONENT_KEYS, 0)
    totals["tokens_total"] = 0
    return totals


def _accumulate_tokens(totals: dict[str, int], row: AttributedRow) -> None:
    totals["tokens_in"] += row.tokens_in
    totals["tokens_out"] += row.tokens_out
    totals["cache_read"] += row.cache_read
    totals["cache_create"] += row.cache_create
    totals["tokens_total"] += row.tokens_in + row.tokens_out + row.cache_read + row.cache_create


@dataclass(frozen=True)
class PipelineBucket:
    """The per-pipeline row every rendered table is a projection of."""

    pipeline_slug: str
    tier: str
    tier_reason: str | None
    attributed_rows: int
    sessions: int
    models: frozenset[str]
    tokens: dict[str, int]
    by_agent_type: dict[str, dict[str, int]]


def build_pipeline_buckets(
    rows: Sequence[AttributedRow], tier_index: dict[str, list[str]]
) -> list[PipelineBucket]:
    """Fold attributed rows into one bucket per `pipeline_slug`.

    The ONE fold every per-pipeline, per-tier, and per-agent-type table
    projects from -- grouping the same bucket list two different ways
    (by tier, by agent type) cannot disagree with a grand total computed
    from the same list, the way three independent scans over raw rows
    could silently drift apart.
    """

    grouped: dict[str, list[AttributedRow]] = {}
    order: list[str] = []
    for row in rows:
        if row.pipeline_slug not in grouped:
            grouped[row.pipeline_slug] = []
            order.append(row.pipeline_slug)
        grouped[row.pipeline_slug].append(row)

    buckets: list[PipelineBucket] = []
    for slug in order:
        slug_rows = grouped[slug]
        tier, tier_reason = _flatten_tier(resolve_tier(slug, tier_index))

        tokens = _empty_token_totals()
        by_agent_type: dict[str, dict[str, int]] = {}
        for row in slug_rows:
            _accumulate_tokens(tokens, row)
            per_type = by_agent_type.setdefault(row.agent_type, _empty_token_totals())
            _accumulate_tokens(per_type, row)

        buckets.append(
            PipelineBucket(
                pipeline_slug=slug,
                tier=tier,
                tier_reason=tier_reason,
                attributed_rows=len(slug_rows),
                sessions=len({row.session_id for row in slug_rows}),
                models=frozenset(row.model for row in slug_rows),
                tokens=tokens,
                by_agent_type=by_agent_type,
            )
        )
    return buckets


def unresolved_agent_type_share(rows: Sequence[AttributedRow]) -> dict[str, Any]:
    """The share of attributed rows whose `agent_type_source` is unresolved.

    A standalone figure, deliberately not folded into any named agent
    type's total -- the unresolved share is about the attributed population
    as a whole, not a per-pipeline breakdown of it.
    """

    total = len(rows)
    unresolved = sum(1 for row in rows if row.agent_type_source == "unresolved")
    share = (unresolved / total) if total else 0
    return {"unresolved_rows": unresolved, "attributed_rows": total, "share": share}


# ---------------------------------------------------------------------------
# Coverage -- the honesty surface, and the dec-378 executable guard.
# ---------------------------------------------------------------------------

# The three WAL-sourced quarantine populations `_audit_totals` reconciles
# against `total_agent_stop_rows`. `summary-rollup-unattributed` is a
# separate, committed-summary-derived population and deliberately excluded
# from this sum -- it is not part of the WAL's own row count.
_WAL_QUARANTINE_KEYS: tuple[str, ...] = (
    Provenance.PARENT_SOURCED.value,
    Provenance.PRE_ATTRIBUTION.value,
    Provenance.UNPARSED.value,
)
_SUMMARY_ROLLUP_QUARANTINE_KEY = "summary-rollup-unattributed"


@dataclass(frozen=True)
class Coverage:
    """The honesty surface -- how few rows a report stands on, and why.

    `duplicates_dropped` defaults to `0` (keyword-safe) so a `Coverage`
    built without it -- as every pre-existing test fixture in this suite
    does -- describes a run where dedup dropped nothing, matching those
    fixtures' own implicit assumption.
    """

    attributed_rows: int
    total_agent_stop_rows: int
    quarantine: dict[str, int]
    duplicate_agent_ids: list[str]
    sessions_durable: int
    sessions_with_slug: int
    sessions_slug_unknown: int
    sources: list[SourceRef]
    duplicates_dropped: int = 0


def summary_row_slug(row: dict) -> str:
    """A committed summary row already carries its slug directly (or
    doesn't, for rows written before this key existed) -- no re-derivation
    to do here, unlike the WAL side's `Path(cwd).name` computation."""

    return row.get("pipeline_slug", "unknown")


def summary_row_is_rollup_unattributed(row: dict) -> bool:
    """True when the row's `tokens_by_agent_type` carries any populated
    rollup -- the provenance-blind population this census quarantines
    rather than ever summing into a total."""

    rollup = row.get("tokens_by_agent_type")
    if not isinstance(rollup, dict) or not rollup:
        return False
    return any(
        isinstance(per_type, dict) and any(value for value in per_type.values())
        for per_type in rollup.values()
    )


def _audit_totals(coverage: Coverage, buckets: list[PipelineBucket]) -> list[str]:
    """Re-derive two counts from independent sources and compare them
    before any total is published -- the dec-378 executable guard.

    **Check 1 (bucket sum vs. census).** `sum(bucket.attributed_rows)` comes
    from the read pass's official, patchable path (`_classify` ->
    `_attributed_from_row` -> `build_pipeline_buckets`). `coverage.attributed_rows`
    comes from `CostCollector.collect`'s independent audit census, which
    classifies via `_partition_provenance` directly -- never through the
    patchable `_classify` name. A correct `_classify` always agrees with
    `_partition_provenance`, so this check is silent in ordinary operation;
    a compromised `_classify` breaks only the bucket side, which this check
    catches.

    **Check 2 (census vs. read pass).** `coverage.total_agent_stop_rows`
    comes from `SourceRef.agent_stop_rows`, summed over the WAL/archive
    sources as the read pass counted them -- before classification, before
    dedup, and never touched by the census that produces
    `coverage.attributed_rows`/`coverage.quarantine`/`coverage.duplicates_dropped`.
    Those three census-side figures are then reconciled against that
    read-side total in one equation: every row the read pass counted must
    either survive dedup as attributed, survive dedup into one of the three
    WAL-sourced quarantine populations, or be a row the census's own dedup
    step reported dropping. Because `duplicates_dropped` is the dedup
    core's own self-reported arithmetic (see `_dedup_by_agent_id`) rather
    than a quantity this function recomputes from list lengths, a defect
    that makes the dedup step silently lose a row without correctly
    reporting the drop is still visible here -- a call-site recompute from
    before/after lengths could never expose that class of defect, since it
    would just re-measure whatever the (possibly buggy) dedup step actually
    returned.
    """

    issues: list[str] = []

    bucket_attributed_sum = sum(bucket.attributed_rows for bucket in buckets)
    if bucket_attributed_sum != coverage.attributed_rows:
        issues.append(
            "provenance invariant violated: bucket attributed-row sum "
            f"({bucket_attributed_sum}) does not match coverage.attributed_rows "
            f"({coverage.attributed_rows})"
        )

    wal_quarantine_sum = sum(coverage.quarantine.get(key, 0) for key in _WAL_QUARANTINE_KEYS)
    reconstructed_total = (
        coverage.attributed_rows + wal_quarantine_sum + coverage.duplicates_dropped
    )
    if reconstructed_total != coverage.total_agent_stop_rows:
        issues.append(
            "provenance invariant violated: attributed_rows + quarantine + "
            f"duplicates_dropped ({reconstructed_total}) does not match "
            f"total_agent_stop_rows ({coverage.total_agent_stop_rows})"
        )

    return issues


# ---------------------------------------------------------------------------
# Standard-vs-Lightweight cell -- the withheld-verdict shape, and the rendered ratio.
# ---------------------------------------------------------------------------

_STANDARD_TIER = "Standard"
_LIGHTWEIGHT_TIER = "Lightweight"


def compute_standard_vs_lightweight_cell(buckets: Sequence[PipelineBucket]) -> dict[str, Any]:
    """Render `n/a` with a reason unless both tiers have >=1 attributed
    row and the Lightweight median is non-zero; the two shapes share no
    numeric key, so a consumer cannot read a ratio out of an `n/a` cell."""

    standard = [b for b in buckets if b.tier == _STANDARD_TIER and b.attributed_rows > 0]
    lightweight = [b for b in buckets if b.tier == _LIGHTWEIGHT_TIER and b.attributed_rows > 0]

    if not standard or not lightweight:
        missing = [
            tier
            for tier, present in (
                (_STANDARD_TIER, standard),
                (_LIGHTWEIGHT_TIER, lightweight),
            )
            if not present
        ]
        return {"status": "n/a", "reason": f"no attributed rows at tier {' and '.join(missing)}"}

    standard_median = statistics.median(bucket.tokens["tokens_total"] for bucket in standard)
    lightweight_median = statistics.median(bucket.tokens["tokens_total"] for bucket in lightweight)
    if lightweight_median == 0:
        # Attributed rows do not imply a non-zero total; a zero divisor is a
        # withheld cell with a reason, never a raise.
        return {"status": "n/a", "reason": f"{_LIGHTWEIGHT_TIER} median is zero tokens"}
    return {
        "status": "rendered",
        "basis": "tokens_total",
        "standard": {"n": len(standard), "median": standard_median},
        "lightweight": {"n": len(lightweight), "median": lightweight_median},
        "ratio": standard_median / lightweight_median,
    }


# ---------------------------------------------------------------------------
# CostCollector -- the class wired into the runner registry.
# ---------------------------------------------------------------------------


def _load_tier_index(repo_root: str, issues: list[str]) -> dict[str, list[str]]:
    path = Path(repo_root) / ".ai-state" / _CALIBRATION_LOG_FILENAME
    if not path.is_file():
        issues.append(f"calibration log not found: {path}")
        return {}
    try:
        return parse_calibration_log(str(path))
    except OSError as exc:
        issues.append(f"calibration log unreadable: {path}: {exc.strerror or exc!r}")
        return {}


def _bucket_to_json(bucket: PipelineBucket) -> dict[str, Any]:
    return {
        "pipeline_slug": bucket.pipeline_slug,
        "tier": bucket.tier,
        "tier_reason": bucket.tier_reason,
        "attributed_rows": bucket.attributed_rows,
        "sessions": bucket.sessions,
        "models": sorted(bucket.models),
        "tokens": dict(bucket.tokens),
        "by_agent_type": {
            agent_type: dict(tokens) for agent_type, tokens in bucket.by_agent_type.items()
        },
    }


def _tier_projection(buckets: Sequence[PipelineBucket]) -> dict[str, Any]:
    """The per-tier table -- a fold over the same buckets, grouped by
    `tier` instead of `pipeline_slug`."""

    projection: dict[str, dict[str, Any]] = {}
    for bucket in buckets:
        entry = projection.setdefault(
            bucket.tier, {"attributed_rows": 0, "tokens": _empty_token_totals(), "pipelines": []}
        )
        entry["attributed_rows"] += bucket.attributed_rows
        for key in entry["tokens"]:
            entry["tokens"][key] += bucket.tokens[key]
        entry["pipelines"].append(bucket.pipeline_slug)
    return projection


def _agent_type_projection(buckets: Sequence[PipelineBucket]) -> dict[str, Any]:
    """The per-agent-type table -- a fold over the same buckets, grouped by
    `agent_type` instead of `pipeline_slug`."""

    projection: dict[str, dict[str, int]] = {}
    for bucket in buckets:
        for agent_type, tokens in bucket.by_agent_type.items():
            entry = projection.setdefault(agent_type, _empty_token_totals())
            for key in entry:
                entry[key] += tokens[key]
    return projection


def _coverage_to_json(coverage: Coverage) -> dict[str, Any]:
    return {
        "attributed_rows": coverage.attributed_rows,
        "total_agent_stop_rows": coverage.total_agent_stop_rows,
        "quarantine": dict(coverage.quarantine),
        "duplicate_agent_ids": list(coverage.duplicate_agent_ids),
        "sessions_durable": coverage.sessions_durable,
        "sessions_with_slug": coverage.sessions_with_slug,
        "sessions_slug_unknown": coverage.sessions_slug_unknown,
        "duplicates_dropped": coverage.duplicates_dropped,
        "sources": [
            {
                "path": source.path,
                "kind": source.kind,
                "checkout": source.checkout,
                "mtime_iso": source.mtime_iso,
                "lines_scanned": source.lines_scanned,
                "agent_stop_rows": source.agent_stop_rows,
                "attributed_rows": source.attributed_rows,
            }
            for source in coverage.sources
        ],
    }


def _read_all_sources(
    sources: Sequence[SourceRef],
) -> tuple[list[tuple[dict, str]], list[dict], list[SourceRef], list[str]]:
    """Read every discovered source once: `(raw_rows, summary_rows,
    read_sources, issues)`. Splits `agent_stop` rows from the committed
    summary census and updates each `SourceRef`'s scanned counts."""

    raw_rows: list[tuple[dict, str]] = []
    summary_rows: list[dict] = []
    read_sources: list[SourceRef] = []
    issues: list[str] = []

    for source in sources:
        if source.kind == _SOURCE_KIND_SUMMARY:
            rows, issue = _read_summary_rows(source.path)
            if issue:
                issues.append(issue)
            summary_rows.extend(rows)
            read_sources.append(dataclasses.replace(source, lines_scanned=len(rows)))
            continue
        rows, issue = read_agent_stop_rows(source.path)
        if issue:
            issues.append(issue)
        raw_rows.extend((row, source.path) for row in rows)
        read_sources.append(
            dataclasses.replace(source, lines_scanned=len(rows), agent_stop_rows=len(rows))
        )

    return raw_rows, summary_rows, read_sources, issues


def _read_side_agent_stop_total(read_sources: Sequence[SourceRef]) -> int:
    """`total_agent_stop_rows`, sourced from the read pass's own per-source
    row counts -- before classification, before dedup, and never derived
    from the census that separately produces `attributed_rows`/
    `quarantine`/`duplicates_dropped`. Summary sources contribute `0` here
    (their `agent_stop_rows` field is never set to anything else), so
    summing unconditionally is safe."""

    return sum(source.agent_stop_rows for source in read_sources)


def _build_official_buckets(
    raw_rows: Sequence[tuple[dict, str]], tier_index: dict[str, list[str]]
) -> tuple[list[AttributedRow], list[PipelineBucket]]:
    """The patchable `_classify` path every rendered table is built from."""

    candidates = [
        attributed
        for row, source_path in raw_rows
        if (attributed := _attributed_from_row(row, source_path)) is not None
    ]
    deduped, _duplicate_ids = dedup_attributed_rows(candidates)
    return deduped, build_pipeline_buckets(deduped, tier_index)


def _independent_audit_census(
    raw_rows: Sequence[tuple[dict, str]],
) -> tuple[dict[Provenance, int], list[str], int]:
    """`(population_counts, duplicate_agent_ids, duplicates_dropped)` -- see
    the module docstring's "Guard independence" note and `_audit_totals`'s
    own docstring. Classifies every row via `_partition_provenance`
    directly, never through the patchable `_classify` name.
    `duplicates_dropped` sums each provenance class's own dedup-reported
    drop count (`_dedup_by_agent_id`'s third return value) -- not a
    recompute from list lengths, so it stays a genuinely independent
    witness of what the dedup step actually did.
    """

    by_provenance: dict[Provenance, list[tuple[str, str]]] = {p: [] for p in Provenance}
    for row, source_path in raw_rows:
        provenance = _partition_provenance(row)
        by_provenance[provenance].append((str(row.get("agent_id", "")), source_path))

    duplicate_agent_ids: list[str] = []
    duplicates_dropped = 0
    counts: dict[Provenance, int] = {}
    for provenance, entries in by_provenance.items():
        deduped_entries, dup_ids, dropped_count = _dedup_by_agent_id(
            entries, agent_id_of=lambda e: e[0], source_path_of=lambda e: e[1]
        )
        counts[provenance] = len(deduped_entries)
        duplicate_agent_ids.extend(dup_ids)
        duplicates_dropped += dropped_count
    return counts, duplicate_agent_ids, duplicates_dropped


def _summary_census(summary_rows: Sequence[dict]) -> tuple[int, int, int]:
    """`(sessions_with_slug, sessions_slug_unknown, rollup_unattributed_count)`."""

    sessions_with_slug = 0
    sessions_slug_unknown = 0
    rollup_unattributed_count = 0
    for row in summary_rows:
        if summary_row_slug(row) == "unknown":
            sessions_slug_unknown += 1
        else:
            sessions_with_slug += 1
        if summary_row_is_rollup_unattributed(row):
            rollup_unattributed_count += 1
    return sessions_with_slug, sessions_slug_unknown, rollup_unattributed_count


def _attach_attributed_counts(
    read_sources: Sequence[SourceRef], official_deduped: Sequence[AttributedRow]
) -> list[SourceRef]:
    """Per-source attributed-row counts, attached after the official build
    has run (`SourceRef` starts at 0 at discovery time; see its own
    docstring)."""

    counts: dict[str, int] = {}
    for row in official_deduped:
        counts[row.source_path] = counts.get(row.source_path, 0) + 1
    return [
        dataclasses.replace(source, attributed_rows=counts.get(source.path, 0))
        for source in read_sources
    ]


class CostCollector(Collector):
    """Token usage per pipeline, per tier, and per agent type -- honest
    rows only, every other population quarantined by name and count."""

    name = "cost"
    tier = 0

    def __init__(self, repo_root: str) -> None:
        self._repo_root = repo_root

    # ------------------------------------------------------------------ resolve

    def resolve(self, env: ResolutionEnv) -> ResolutionResult:
        """Available when either observability artifact exists; otherwise
        not applicable -- a repository that never ran Praxion observability
        is silently skipped rather than reporting a misleading zero."""

        del env  # unused -- no PATH lookup needed, just a filesystem check
        ai_state = Path(self._repo_root) / ".ai-state"
        if (ai_state / _SUMMARY_FILENAME).is_file() or (ai_state / _WAL_FILENAME).is_file():
            return Available(version="", details={})
        return NotApplicable(reason="no observability artifacts under .ai-state/")

    # ------------------------------------------------------------------ collect

    def _resolve_repo_root(self, ctx: CollectionContext) -> Path:
        """Prefer the constructor root; fall back to ctx, then the cwd.

        The runner threads the literal `"."` through `ctx.repo_root`, so the
        constructor value is the authoritative one -- the readiness
        collector's precedent. Resolved, so every path derived from it is
        absolute and names its checkout.
        """

        if self._repo_root and self._repo_root != ".":
            return Path(self._repo_root).resolve()
        if ctx.repo_root and ctx.repo_root != ".":
            return Path(ctx.repo_root).resolve()
        return Path.cwd()

    def collect(self, ctx: CollectionContext) -> CollectorResult:
        """Read pass, then aggregate pass, then the provenance guard."""

        repo_root = str(self._resolve_repo_root(ctx))
        sources, discover_issues = discover_sources(repo_root)
        tier_index = _load_tier_index(repo_root, discover_issues)
        raw_rows, summary_rows, read_sources, read_issues = _read_all_sources(sources)
        issues = [*discover_issues, *read_issues]

        official_deduped, buckets = _build_official_buckets(raw_rows, tier_index)
        audit_counts, duplicate_agent_ids, duplicates_dropped = _independent_audit_census(raw_rows)
        sessions_with_slug, sessions_slug_unknown, rollup_unattributed = _summary_census(
            summary_rows
        )

        quarantine = {
            Provenance.PARENT_SOURCED.value: audit_counts[Provenance.PARENT_SOURCED],
            Provenance.PRE_ATTRIBUTION.value: audit_counts[Provenance.PRE_ATTRIBUTION],
            Provenance.UNPARSED.value: audit_counts[Provenance.UNPARSED],
            _SUMMARY_ROLLUP_QUARANTINE_KEY: rollup_unattributed,
        }
        coverage = Coverage(
            attributed_rows=audit_counts[Provenance.ATTRIBUTED],
            total_agent_stop_rows=_read_side_agent_stop_total(read_sources),
            quarantine=quarantine,
            duplicate_agent_ids=duplicate_agent_ids,
            sessions_durable=len(summary_rows),
            sessions_with_slug=sessions_with_slug,
            sessions_slug_unknown=sessions_slug_unknown,
            sources=_attach_attributed_counts(read_sources, official_deduped),
            duplicates_dropped=duplicates_dropped,
        )

        audit_issues = _audit_totals(coverage, buckets)
        if audit_issues:
            return CollectorResult(status="error", data={}, issues=[*audit_issues, *issues])

        data = {
            "pipelines": [_bucket_to_json(bucket) for bucket in buckets],
            "tiers": _tier_projection(buckets),
            "agent_types": _agent_type_projection(buckets),
            "unresolved_agent_type_share": unresolved_agent_type_share(official_deduped),
            "coverage": _coverage_to_json(coverage),
            "standard_vs_lightweight": compute_standard_vs_lightweight_cell(buckets),
        }
        status = "partial" if issues else "ok"
        return CollectorResult(status=status, data=data, issues=issues)
