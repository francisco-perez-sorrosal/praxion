"""Cost collector -- read pass plus aggregate pass.

This module reads the observability write-ahead log (the observation log
under `.ai-state/` and every retained archive) plus the committed per-session summary rollup
across the main checkout and every sibling worktree, classifies each
`agent_stop` row by how honestly its token usage was attributed, and
de-duplicates the honest population by `agent_id` (the read pass). It then
joins each pipeline to a calibration tier, folds the honest rows into one
bucket list that every per-pipeline/per-tier/per-agent-type table projects
from, re-derives its own totals before publishing them, and exposes the
`CostCollector` class the runner registers (the aggregate pass).

The four-way honesty classification (`Provenance`, `_classify`,
`_partition_provenance`), `AttributedRow`'s shape, the low-level
source-discovery seam, the streaming JSONL reader and the dedup core live in
`cost_collector_read.py`; the tier join in `cost_collector_tier.py`; the JSON
projections in `cost_collector_report.py`. All are re-exported from here.

Patch seams (why some read-pass code is defined here)
-----------------------------------------------------
Tests monkeypatch names on *this* module object. A bare-name call resolves
through the calling function's own defining module, so a caller that must
observe a patch has to be defined here, not in a sibling that imports the
same object. Four callers are pinned for that reason:

- `_attributed_from_row` calls `_classify` -- the fault-injection test
  replaces `_classify` and expects the guard to reject the result.
- `discover_sources` calls `_resolve_main_checkout` -- `TestDiscoverSources`
  asserts on the patched checkout, and the fault-injection and
  production-wiring tests patch it only to stay off real git. Moved, the
  first would fail loudly; the others would keep passing while shelling out
  to `git rev-parse`, which is the silent half of the hazard.
- `dedup_attributed_rows` and `_independent_audit_census` call
  `_dedup_by_agent_id` -- the miscounted-dedup test replaces it and expects
  the guard to catch the misreport. Its fixture reaches only the census;
  keeping both callers here keeps the patch reaching the official path too.

Moving any of these to a sibling module is a behaviour change for the test
suite even when every test still passes.

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
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hooks._observation_log import reader
from scripts.project_metrics.collectors.base import (
    Available,
    CollectionContext,
    Collector,
    CollectorResult,
    NotApplicable,
    ResolutionEnv,
    ResolutionResult,
)
from scripts.project_metrics.collectors.cost_collector_read import (
    AttributedRow,
    Provenance,
    SourceRef,
    _classify,
    _dedup_by_agent_id,
    _is_int_coercible,
    _mtime_iso,
    _partition_provenance,
    _read_summary_rows,
    _resolve_main_checkout,
    read_agent_stop_rows,
)
from scripts.project_metrics.collectors.cost_collector_report import (
    _accumulate_tokens,
    _agent_type_projection,
    _bucket_to_json,
    _coverage_to_json,
    _empty_token_totals,
    _tier_projection,
)
from scripts.project_metrics.collectors.cost_collector_tier import (
    TierAmbiguous,
    TierResolved,
    TierUnknown,
    _flatten_tier,
    parse_calibration_log,
    resolve_tier,
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

# ---------------------------------------------------------------------------
# Tunables and named constants.
# ---------------------------------------------------------------------------

_WAL_FILENAME = reader.LOG_FILENAME
_SUMMARY_FILENAME = "observations_summary.jsonl"
_CALIBRATION_LOG_FILENAME = "calibration_log.md"

# SourceRef.kind values -- named here so discover_sources never repeats a
# bare string literal at each of its three enumeration call sites.
_SOURCE_KIND_WAL = "wal"
_SOURCE_KIND_WAL_ARCHIVE = "wal-archive"
_SOURCE_KIND_SUMMARY = "summary"


# ---------------------------------------------------------------------------
# AttributedRow construction -- the sole `_classify`-observing call site.
# ---------------------------------------------------------------------------


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

    Defined here, not in `cost_collector_read.py`: its bare `_classify`
    call is a patch seam (module docstring, "Patch seams").
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

    Defined here, not in `cost_collector_read.py`: its bare
    `_dedup_by_agent_id` call is a patch seam (module docstring, "Patch
    seams").
    """

    deduped, duplicate_agent_ids, _dropped_count = _dedup_by_agent_id(
        rows, agent_id_of=lambda row: row.agent_id, source_path_of=lambda row: row.source_path
    )
    return deduped, duplicate_agent_ids


# ---------------------------------------------------------------------------
# Source discovery -- the enumeration entry point over the injectable git seam.
# ---------------------------------------------------------------------------


def discover_sources(repo_root: str) -> tuple[list[SourceRef], list[str]]:
    """Enumerate every WAL/archive/summary file across the repository's checkouts.

    Enumerates `[repo_root, main_checkout, *sibling_worktrees]` for WAL and
    archive files first, then the same checkout list for the committed
    summary file -- two full passes, not one pass interleaving kinds per
    checkout, so the discovered order is stable regardless of which checkout
    the collector runs from -- the property that lets every checkout see the
    same source set, so a report from a worktree and one from main agree.
    A checkout's segments come from the log reader's discovery: the active
    log first, then each archive from the newest, so across files the newer
    segment keeps an `agent_id` the dedup sees twice. An archive position
    missing between present ones is an `issues` entry naming its path.
    A file is only included when it exists; de-duplication is by resolved
    path, so a checkout that happens to equal `repo_root` (or one already
    seen under another name) contributes its files exactly once.

    Defined here, not in `cost_collector_read.py`: its bare
    `_resolve_main_checkout` call is a patch seam (module docstring,
    "Patch seams").
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

    def _add(dir_path: Path, kind: str, candidate: Path) -> None:
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
        listing = reader.segment_listing(dir_path / ".ai-state", archives=True)
        for gap in listing.missing:
            issue = f"missing log archive between present archives: {gap}"
            if issue not in issues:  # a checkout reached twice names its gaps once
                issues.append(issue)
        for segment in reversed(listing.segments):
            kind = _SOURCE_KIND_WAL if segment.name == _WAL_FILENAME else _SOURCE_KIND_WAL_ARCHIVE
            _add(dir_path, kind, segment)
    for dir_path in checkout_dirs:
        _add(dir_path, _SOURCE_KIND_SUMMARY, dir_path / ".ai-state" / _SUMMARY_FILENAME)

    return sources, issues


# ---------------------------------------------------------------------------
# Pipeline bucket aggregation -- one bucket list, three projections.
# ---------------------------------------------------------------------------


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
    witness of what the dedup step actually did. Its bare
    `_dedup_by_agent_id` call is a patch seam (module docstring, "Patch
    seams").
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
