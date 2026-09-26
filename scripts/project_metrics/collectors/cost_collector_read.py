"""Cost collector -- read-pass primitives.

Companion module to `cost_collector.py`: the four-way honesty classification,
`AttributedRow`'s shape, the low-level source-discovery seam, the streaming
JSONL reader, and the last-in-file/first-across-file dedup core
(`_dedup_by_agent_id`). Split out of
`cost_collector.py` purely for module size -- every name here is imported
back into `cost_collector.py` and re-exported from its `__all__` unchanged.

`discover_sources`, `_attributed_from_row` and `dedup_attributed_rows` stay
in `cost_collector.py` -- see that module's "Patch seams" section.

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
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import TypeVar

_T = TypeVar("_T")

# Mirrors git_collector.py's own subprocess-timeout pattern: a single, bounded
# `git rev-parse` call must never hang this collector.
_GIT_SUBPROCESS_TIMEOUT_SECONDS: float = 10.0

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
    this exact symbol. See the module docstring's "Guard independence" note
    in `cost_collector.py`.
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
    `_attributed_from_row` in `cost_collector.py`) -- a downstream consumer
    never has to re-check for `None`.
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


# ---------------------------------------------------------------------------
# SourceRef -- one discovered WAL/archive/summary file.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceRef:
    """One file `discover_sources` (in `cost_collector.py`) found on disk.

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
# Source discovery -- the injectable git seam `discover_sources` calls.
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
    provenance-agnostic dedup (see `_audit_totals`'s guard in
    `cost_collector.py`) apply the exact same rule -- a genuine divergence
    between the two is then only possible when the classification feeding
    them differs, never when the dedup algorithm itself does.

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
