#!/usr/bin/env python3
"""Deterministic pipeline step-completion reconciler.

Answers "did this pipeline step actually complete?" from **ground truth**, not
from the agent-authored `WIP.md` checkbox. A subagent hard-truncated at its
context ceiling can finish real work but die before flipping its checkbox (or
leave a stale `[COMPLETE]` claim). This reader verifies each step's claim
against a three-tier reliability hierarchy and emits a per-step verdict that
`/resume-pipeline` consumes.

Reliability hierarchy (the spine):
  Tier 1 (arbiter)        — codebase + `git diff` + `TEST_RESULTS.md` (either
                            the legacy free-form pytest-summary shape or the
                            canonical `Result: pass=<n> fail=<n> skip=<n>`
                            per-step shape, dec-386 — see `step_test_status`).
  Tier 2 (localization)   — the observation log (the harness WAL, owned by
                            `_observation_log`): which agent stopped, where it
                            last wrote. Only ever *adds* a hint; never
                            *overrides* a Tier-1 verdict.
  Tier 3 (never trusted)  — the `WIP.md` checkbox itself, validated here.

Entry point: ``reconcile(slug, repo_root, base_ref) -> list[verdict]`` is a pure,
side-effect-free function (no writes, no git mutation) — trivially unit-testable
via the ``_*_override`` hooks, and safe to run read-only at any pipeline seam.

Verdict ∈ {verified-complete, mismatch, partial, in-flight, unknown, pending,
blocked, attempts-exhausted}. Tier-1 is always the arbiter: when correlation is
ambiguous or the WAL dropped a line, a step degrades to `unknown` (surfaced to
the user) — never to a guessed `verified-complete`. The WAL can only sharpen
localization, never certify work. `blocked` is an otherwise-done step the plan
tags `mutation: on` whose results carry no usable mutation reading;
`attempts-exhausted` is a step that used its fresh attempts (its `WIP.md`
`Attempts:` count) without being verified complete.

A step's plan `Check:` line is judged against the `Result:` recorded for that
step in `TEST_RESULTS.md` — only read, never run; a step with none is decided by
its files and tests. Each verdict also carries `decided_by` (`check`, `fallback`
or `none`), `outcome_source` (only when a check decided: `run` when the deciding
`Result:` line is the step-loop driver's own run, else `recorded`) and `attempt`
(only when `WIP.md` records a count).

An `Attempts:` line may name the step-loop driver's request (`request=<id>`). The
task's iteration ledger records each request that ended; a request it does not
hold is outstanding, so a step not verified complete reads `in-flight`, never
`attempts-exhausted`, until its attempt has been recorded. A `WIP.md` without
the token reads exactly as before. ``reconcile(..., assume_recorded=...)`` gives
the verdict as it will read once the named requests are recorded. A ledger line
that breaks the record shape (a truncated append, a hand edit, a merge conflict)
may be the end of any outstanding request, so while the ledger holds one, a step
whose attempt is outstanding reads `unknown`, naming the line, and not `in-flight`;
a recorded attempt is unaffected.

An `Attempts:` line that names a step but breaks the grammar (a zero or
non-numeric count) makes that step `unknown`, with exit status 2. A line under
another label (`Attempt:`) is not an attempts line by the grammar and is
ignored, by design. A labelled line that names no step (`step 3 count=2`) binds
to no step, so it is reported apart: `main` writes it to stderr, in both output
modes, and exits 2. The JSON output on stdout is the verdict array in every case.

Exit codes: 0 nothing to recover; 1 >=1 step needs recovery
(mismatch/partial/in-flight); 2 >=1 unknown, blocked or attempts-exhausted
(needs human), or an `Attempts:` line naming no step; 3 reconcile error.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from _loop_fields import (
    Check,
    CheckLine,
    OutstandingAttempt,
    evaluate_check,
    parse_attempts,
    parse_step_checks,
)
from _plan_steps import scan_step_files, split_files
from _repo_root import is_plugin_cache_path, resolve_repo_root
from _step_schema import (
    RecordedRun,
    mutation_block_reasons,
    parse_wip_claims,
    recorded_runs,
    step_sort_key,
    step_test_status,
)
from _step_verdict import (
    HUMAN_VERDICTS,
    VERDICT_WORDS,
    AttemptRecord,
    DeclaredCheck,
    StepEvidence,
    UnreadableAttempts,
    classify_step,
)
from iteration_ledger import LedgerReading, read_ledger

SCRIPT_DIR = Path(__file__).resolve().parent

# hooks/_observation_log is a sibling package to this file's own scripts/
# directory -- both live one level under the repo root.
sys.path.insert(0, str(SCRIPT_DIR.parent / "hooks"))
from _observation_log import reader, retention  # noqa: E402 (after sys.path injection)

# Only step-executing agent types can be correlated to a WIP step verdict;
# research / doc / context agents touch files for other reasons.
STEP_EXECUTING_AGENT_TYPES = frozenset(
    {
        "praxion:implementer",
        "praxion:test-engineer",
        "praxion:implementation-planner",
        "implementer",
        "test-engineer",
        "implementation-planner",
    }
)

# ---------------------------------------------------------------------------
# Public entry point — pure, side-effect-free
# ---------------------------------------------------------------------------


def reconcile(
    slug: str,
    repo_root: Path | str,
    base_ref: str | None,
    *,
    state_root: Path | str | None = None,
    max_age_days: int = 7,
    _changed_files_override: list[str] | None = None,
    _wal_rows_override: list[dict[str, Any]] | None = None,
    _test_status_override: str | None = None,
    assume_recorded: frozenset[str] = frozenset(),
    include_untracked: bool = False,
) -> list[dict[str, Any]]:
    """Reconcile every step in ``.ai-work/<slug>/WIP.md`` against ground truth.

    ``repo_root`` is passed explicitly so the function works in any cwd; the
    ``_*_override`` hooks inject the three external reads (git diff, the WAL, the
    test status) for hermetic runs. ``state_root`` locates ``.ai-state/`` and
    ``.ai-work/`` when they live outside the git repo (Standard-tier worktrees).
    ``assume_recorded`` names requests to read as recorded in the iteration
    ledger though they are not yet, so a caller about to record one sees the
    verdict the reconciler will give once it has. ``include_untracked`` counts new, not yet
    committed files as changed: a driver that gates a step before committing it needs that,
    while a reader asking what is still uncommitted (the handoff composer) must not read an
    untracked file as proof its step finished.

    Returns one verdict dict per WIP step (see module docstring for the shape),
    or ``[]`` when there is no ``WIP.md`` for the slug (graceful degrade).
    """
    repo_root = Path(repo_root)
    state_root = Path(state_root) if state_root is not None else repo_root
    task_dir = state_root / ".ai-work" / slug
    claims = _parse_wip_steps(task_dir / "WIP.md")  # {} when WIP.md is absent or has no steps
    if not claims:
        return []

    changed_files = _changed_files(repo_root, base_ref, include_untracked, _changed_files_override)
    wal_rows = _wal_rows(state_root, max_age_days, _wal_rows_override)
    ledger = read_ledger(task_dir)
    recorded = _RecordedRequests(ledger.requests | assume_recorded, _findings_text(ledger))
    gathered = _gather(task_dir, changed_files, wal_rows, _test_status_override, recorded)
    return [
        _reconcile_step(step_id, claims[step_id], gathered)
        for step_id in sorted(claims, key=step_sort_key)
    ]


def _changed_files(
    repo_root: Path, base_ref: str | None, include_untracked: bool, override: list[str] | None
) -> set[str]:
    """The files changed since ``base_ref``, or the injected ``override`` for a hermetic run."""
    if override is not None:
        return set(override)
    return _git_changed_files(repo_root, base_ref, include_untracked)


def _wal_rows(
    state_root: Path, max_age_days: int, override: list[dict[str, Any]] | None
) -> list[dict[str, Any]]:
    """The recent WAL rows, or the injected ``override`` for a hermetic run."""
    if override is not None:
        return override
    return _read_wal(reader.log_path(state_root / ".ai-state"), max_age_days=max_age_days)


def _gather(
    task_dir: Path,
    changed_files: set[str],
    wal_rows: list[dict[str, Any]],
    test_status_override: str | None,
    recorded_requests: _RecordedRequests,
) -> _Gathered:
    """Read the plan, ``WIP.md`` and ``TEST_RESULTS.md`` and parse what they declare.

    The declared-files scan re-reads the plan (``WIP.md`` as fallback) itself.
    ``recorded_requests`` are the requests the ledger holds as ended, with its findings.
    """
    plan_path, wip_path = task_dir / "IMPLEMENTATION_PLAN.md", task_dir / "WIP.md"
    plan_text, wip_text = _read_text(plan_path), _read_text(wip_path)
    # `test_status_override` (the test hook) isolates the run from the results
    # file entirely, so a hermetic run sees no results.
    results_text = (
        "" if test_status_override is not None else _read_text(task_dir / "TEST_RESULTS.md")
    )
    return _Gathered(
        declared_files=_parse_plan_files(plan_path, wip_path),
        changed_files=changed_files,
        wal_rows=wal_rows,
        # A per-step pool; empty under the override, which never consults it.
        test_runs=recorded_runs(results_text),
        test_status_override=test_status_override,
        mutation_blocks=mutation_block_reasons(plan_text or wip_text, results_text),
        checks=parse_step_checks(plan_text),
        results_text=results_text,
        attempts=_attempt_records(wip_text, recorded_requests),
    )


@dataclass(frozen=True)
class _Gathered:
    """Everything read from the outside world, ready for the pure per-step verdict."""

    declared_files: dict[str, list[str]]
    changed_files: set[str]
    wal_rows: list[dict[str, Any]]
    test_runs: list[RecordedRun]
    test_status_override: str | None
    mutation_blocks: dict[str, str]
    checks: dict[str, CheckLine]
    results_text: str
    attempts: dict[str, AttemptRecord]


@dataclass(frozen=True)
class _RecordedRequests:
    """The requests the ledger records as ended, and its unreadable lines ("" when none)."""

    requests: frozenset[str]
    findings: str


def _findings_text(ledger: LedgerReading) -> str:
    return "; ".join(f"record {item.position}: {item.reason}" for item in ledger.findings)


def _attempt_records(wip_text: str, recorded: _RecordedRequests) -> dict[str, AttemptRecord]:
    """A count per readable ``Attempts:`` line, outstanding when the ledger has not
    recorded its request; an unreadable line, or an outstanding attempt the ledger's
    unreadable lines may have ended, outranks any count."""
    reading = parse_attempts(wip_text, recorded.requests)
    broken = {step: UnreadableAttempts(why) for step, why in reading.unreadable.items()}
    unsettled = {
        step: UnreadableAttempts(
            recorded.findings, f"the iteration ledger record ending request {attempt.request}"
        )
        for step, attempt in reading.counts.items()
        if isinstance(attempt, OutstandingAttempt) and recorded.findings
    }
    return {**reading.counts, **unsettled, **broken}


def _reconcile_step(step_id: str, claim: str, gathered: _Gathered) -> dict[str, Any]:
    # `attributable()` files only -- a file another step also declares isn't enough.
    declared, runs = gathered.declared_files, gathered.test_runs
    override = gathered.test_status_override
    files = attributable(step_id, declared)
    changed = [f for f in files if _path_in_changeset(f, gathered.changed_files)]
    evidence = StepEvidence(
        step_id=step_id,
        claim=claim,
        files=files,
        changed=changed,
        unchanged=[f for f in files if f not in changed],
        test_status=override if override is not None else step_test_status(step_id, runs),
        tier2=_correlate_agents(files, gathered.wal_rows),
        earlier_declarers=_earlier_declarers(step_id, declared) if not files else [],
        mutation_block=gathered.mutation_blocks.get(step_id),
    )
    return classify_step(
        evidence, _declared_check(step_id, gathered), gathered.attempts.get(step_id)
    )


def _declared_check(step_id: str, gathered: _Gathered) -> DeclaredCheck:
    """None when the step declares no check; the broken line when it cannot be read."""
    declared = gathered.checks.get(step_id)
    if isinstance(declared, Check):
        return evaluate_check(declared, step_id, gathered.results_text)
    return declared


# ---------------------------------------------------------------------------
# Tier-2 correlation — observation-log WAL, file-containment first
# ---------------------------------------------------------------------------


def _correlate_agents(files: list[str], wal_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Correlate a step's files back to the WAL agents that wrote them.

    Direction is *backward* (files -> agents) because the WAL carries no task
    slug. Primary key: file-path containment. Only step-executing agent types
    are considered. Returns a Tier-2 hint that never decides a verdict alone.
    """
    empty = {
        "correlated_agent_ids": [],
        "agent_stop_seen": False,
        "last_write": None,
        "last_write_ts": None,
    }
    if not files:
        return empty

    tool_rows = [r for r in wal_rows if r.get("event_type") == "tool_use"]
    correlated = [
        r
        for r in tool_rows
        if r.get("agent_type") in STEP_EXECUTING_AGENT_TYPES
        and any(_path_match(f, p) for f in files for p in (r.get("file_paths") or []))
    ]
    if not correlated:
        return empty

    agent_ids = sorted({r.get("agent_id", "") for r in correlated if r.get("agent_id")})
    stops = {
        r.get("agent_id")
        for r in wal_rows
        if r.get("event_type") == "agent_stop" and r.get("agent_id") in agent_ids
    }
    latest = max(correlated, key=lambda r: r.get("timestamp", ""))
    last_paths = latest.get("file_paths") or [None]
    return {
        "correlated_agent_ids": agent_ids,
        "agent_stop_seen": bool(stops),
        "last_write": last_paths[-1],
        "last_write_ts": latest.get("timestamp"),
    }


# ---------------------------------------------------------------------------
# Parsing helpers (pure)
# ---------------------------------------------------------------------------


def _parse_wip_steps(wip_path: Path) -> dict[str, str]:
    """Map ``Step N`` -> claim {COMPLETE, IN-PROGRESS, PENDING, AMBIGUOUS} from
    WIP.md -- a thin reader over the shared three-source claim parser."""
    try:
        content = wip_path.read_text(encoding="utf-8")
    except OSError:
        return {}
    return parse_wip_claims(content)


def _parse_plan_files(plan_path: Path, wip_path: Path) -> dict[str, list[str]]:
    """Map ``Step N`` -> declared file list from IMPLEMENTATION_PLAN.md.

    Falls back to scanning WIP.md when the plan is absent (parallel-mode WIP can
    carry per-step Files). Missing/empty is the common case and is handled by
    the classifier (-> unknown), never papered over.
    """
    return _scan_step_files(plan_path) or _scan_step_files(wip_path)


def _scan_step_files(path: Path) -> dict[str, list[str]]:
    """Scan a plan/WIP doc on disk for each step's declared ``Files:``."""
    return scan_step_files(_read_text(path))


_split_files = split_files  # the reader moved to _plan_steps; the old private name stays


def _read_text(path: Path) -> str:
    """A file's text, or "" when it does not exist or cannot be read."""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _read_wal(
    obs_path: Path,
    *,
    max_age_days: int = 7,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Read the observation log's segments within an age window, oldest row first.

    The window is each row's own recorded time, whichever segment holds it --
    rows merged in from a worktree sit in the active log with old times and
    must not widen what recovery considers. Archives are walked newest first
    only while each archive's mtime is inside the window: an older archive
    cannot hold a row newer than the one that ended the walk.

    A row with no readable time is the one exception: in the active log it is
    kept, because it may belong to the session in progress (a bad correlation
    degrades to unknown, never to a false verdict); in an archive it is
    dropped. Rows are ordered by recorded time, never by arrival, so a merge
    cannot change a verdict. A segment that cannot be read is named on
    stderr and the rest are still read.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max_age_days)
    listing = reader.segment_listing(obs_path.parent, archives=True)

    archives = _archives_inside_window(
        [path for path in listing.segments if path != obs_path], cutoff
    )
    _warn_of_gaps(listing.missing, archives)

    rows = [
        row
        for path in (*archives, obs_path)
        for row in _read_segment_or_warn(path).rows
        if _inside_window(row, cutoff, untimed_is_inside=path == obs_path)
    ]
    return sorted(rows, key=reader.row_time)


def _archives_inside_window(archives: list[Path], cutoff: datetime) -> tuple[Path, ...]:
    """The archives (oldest first) from position 1 up to the first one older than ``cutoff``."""
    inside: list[Path] = []
    for path in reversed(archives):  # position 1, the newest, first
        if _modified_at(path) < cutoff:
            break
        inside.append(path)
    return tuple(reversed(inside))


def _modified_at(path: Path) -> datetime:
    """When ``path`` was last written; a file that cannot be examined counts as current,
    so reading it names the problem instead of the walk hiding it."""
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    except OSError:
        return datetime.max.replace(tzinfo=timezone.utc)


def _warn_of_gaps(missing: tuple[Path, ...], archives: tuple[Path, ...]) -> None:
    """Name each archive position absent inside the range ``archives`` covers.

    A position missing beyond the oldest archive read is outside the window
    anyway; one inside it is history lost, not the end of it.
    """
    if not archives:
        return
    oldest_read = _position(archives[0])
    for path in missing:
        if _position(path) < oldest_read:
            print(
                f"reconcile_pipeline_state: wal-gap: {path}; "
                "Tier-2 localization hints may be incomplete",
                file=sys.stderr,
            )


def _position(archive: Path) -> int:
    position = retention.archive_position(archive, reader.LOG_FILENAME)
    assert position is not None, f"not an archive of the log: {archive}"
    return position


def _inside_window(row: dict[str, Any], cutoff: datetime, *, untimed_is_inside: bool) -> bool:
    recorded = reader.row_time(row)
    if recorded == reader.UNTIMED:
        return untimed_is_inside
    return recorded >= cutoff


def _read_segment_or_warn(path: Path) -> reader.SegmentRead:
    """Read one log segment; name an unreadable one on stderr.

    The log is only a Tier-2 localization hint, so reconciliation proceeds
    without it -- but an unreadable log must not pass for an empty one, or
    the missing hint looks like \"no agent touched these files\". An absent
    segment is a normal state and stays silent.
    """
    segment = reader.read_segment(path)
    if segment.error is not None and segment.error != "missing":
        print(
            f"reconcile_pipeline_state: wal-unreadable: {path}: {segment.error}; "
            "Tier-2 localization hints are unavailable",
            file=sys.stderr,
        )
    return segment


def _git_changed_files(
    repo_root: Path, base_ref: str | None, include_untracked: bool = False
) -> set[str]:
    """Repo-relative paths changed vs base_ref, plus the dirty working tree (and, on request,
    untracked files)."""
    changed: set[str] = set()
    diff_targets = []
    if base_ref:
        diff_targets.append(["git", "diff", "--name-only", base_ref])
    diff_targets.append(["git", "diff", "--name-only", "HEAD"])  # unstaged + staged-vs-HEAD
    diff_targets.append(["git", "diff", "--name-only", "--cached"])  # staged
    if include_untracked:
        diff_targets.append(["git", "ls-files", "--others", "--exclude-standard"])
    for cmd in diff_targets:
        try:
            out = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, check=True)
            changed.update(line.strip() for line in out.stdout.splitlines() if line.strip())
        except subprocess.CalledProcessError:
            continue
    return changed


# ---------------------------------------------------------------------------
# Path matching
# ---------------------------------------------------------------------------


def _path_match(declared: str, candidate: str) -> bool:
    """Match a declared file against a WAL/git path. ``declared`` may be a literal
    path or a glob (``scenarios/*.yaml``) — git emits concrete paths, so a glob in
    a step's Files: must be expanded or it never matches (a false mismatch)."""
    d = declared.strip().strip("`").replace("\\", "/")
    c = str(candidate).replace("\\", "/")
    if not d or not c:
        return False
    if any(ch in d for ch in "*?["):
        # Anchored: a glob declaration matches the full candidate path or the
        # candidate under any leading directory, never a bare basename — a
        # basename-only fallback here let a declared `dir/*` match any changed
        # file anywhere in the repo, making glob declarations vacuous evidence.
        return fnmatch.fnmatch(c, d) or fnmatch.fnmatch(c, "*/" + d)
    return (
        c == d
        or c.endswith("/" + d)
        or d.endswith("/" + c)
        or (Path(c).name == Path(d).name and d in c)
    )


def _path_in_changeset(declared: str, changed_files: set[str]) -> bool:
    """True if a declared file appears in the git changeset (suffix-aware)."""
    return any(_path_match(declared, c) for c in changed_files)


# ---------------------------------------------------------------------------
# Shared-file attribution — earliest declarer
# ---------------------------------------------------------------------------


def _files_overlap(a: str, b: str) -> bool:
    """Two declared ``Files:`` entries name the same file. Literal-vs-literal
    and literal-vs-glob reuse ``_path_match``'s own rules (one path-equivalence
    definition for the whole module); glob-vs-glob is string equality only —
    expanding two globs against each other is out of scope (a declared limit).
    """
    a_glob = any(ch in a for ch in "*?[")
    b_glob = any(ch in b for ch in "*?[")
    if a_glob and b_glob:
        return a.strip().strip("`") == b.strip().strip("`")
    if b_glob:
        a, b = b, a  # `_path_match`'s first argument is the glob side
    return _path_match(a, b)


def attributable(step: str, declared: dict[str, list[str]]) -> list[str]:
    """The declared files of ``step`` that no *earlier* step (by
    ``step_sort_key``) also declares. Steps sharing a file are assumed to
    execute in that order; when real work happens out of order, the earliest
    declarer still absorbs the file — a declared limit, not a defect this
    function guards against (see td-255).
    """
    own = declared.get(step, [])
    earlier_files = [
        f
        for other_step, files in declared.items()
        if step_sort_key(other_step) < step_sort_key(step)
        for f in files
    ]
    return [f for f in own if not any(_files_overlap(f, other) for other in earlier_files)]


def _earlier_declarers(step: str, declared: dict[str, list[str]]) -> list[str]:
    """Every earlier step that already claims at least one of ``step``'s
    files, earliest first -- named in the evidence so a human can settle
    every shared file, not just whichever was absorbed first."""
    own = declared.get(step, [])
    earlier = sorted(
        (s for s in declared if step_sort_key(s) < step_sort_key(step)), key=step_sort_key
    )
    return [s for s in earlier if any(_files_overlap(f, o) for f in own for o in declared[s])]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

_RECOVERY_VERDICTS = ("mismatch", "in-flight")


def _needs_recovery(verdict: str) -> bool:
    return verdict in _RECOVERY_VERDICTS or verdict.startswith("partial")


def unnamed_attempts(slug: str, state_root: Path | str) -> list[str]:
    """The `Attempts:` lines in ``WIP.md`` that name no step, as written."""
    wip_text = _read_text(Path(state_root) / ".ai-work" / slug / "WIP.md")
    return list(parse_attempts(wip_text).unnamed)


def _exit_code(verdicts: list[dict[str, Any]], unnamed: tuple[str, ...] | list[str] = ()) -> int:
    """0 clean; 1 recovery needed; 2 a human must decide: a human verdict, or a
    count that binds to no step (the cap may be off for one)."""
    kinds = {v["verdict"] for v in verdicts}
    if unnamed or kinds & set(HUMAN_VERDICTS):
        return 2
    if any(_needs_recovery(k) for k in kinds):
        return 1
    return 0


def _readable_line(v: dict[str, Any]) -> str:
    """`<step>  <verdict>  <decided_by>  [attempt <n>]  <evidence>`."""
    attempt = f"attempt {v['attempt']}  " if "attempt" in v else ""
    return f"{v['step']:>9}  {v['verdict']:<22}  {v['decided_by']:<8}  {attempt}{v['evidence']}"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Reconcile pipeline step-completion against ground truth (read-only). "
            f"Verdicts: {', '.join(VERDICT_WORDS)}; attempts-exhausted exits 2 (a human decides). "
            "A declared Check: is judged against the recorded Result:, never run. Each "
            "verdict carries decided_by, outcome_source (when a check decided) and attempt "
            "(when recorded). An attempt whose request the iteration ledger has not recorded "
            "reads in-flight. "
            "An Attempts: line naming no step is reported on stderr and exits 2."
        )
    )
    parser.add_argument("slug", help="task slug under .ai-work/<slug>/")
    parser.add_argument("--repo-root", default=None, help="git repo root (default: git rev-parse)")
    parser.add_argument(
        "--worktree-root",
        default=None,
        help="root holding .ai-state/ and .ai-work/ (default: --repo-root)",
    )
    parser.add_argument("--base-ref", default=None, help="git ref to diff against (e.g. main)")
    parser.add_argument("--json", action="store_true", help="emit the verdict JSON array on stdout")
    parser.add_argument("--quiet", action="store_true", help="suppress the human summary")
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=7,
        help="max age in days of a log row; bounds every segment, active log included (default: 7)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    repo_root = resolve_repo_root(args.repo_root, script_dir=SCRIPT_DIR)
    if is_plugin_cache_path(repo_root):
        sys.stderr.write(
            "reconcile_pipeline_state: refusing to run against a plugin-cache path; "
            "pass --repo-root or run from the consumer worktree\n"
        )
        return 3
    state_root = Path(args.worktree_root).resolve() if args.worktree_root else repo_root

    if not args.quiet and not reader.log_path(state_root / ".ai-state").exists():
        sys.stderr.write(
            "reconcile_pipeline_state: no local WAL -- Tier-2 correlation skipped, "
            "Tier-1 (git diff + tests) verdicts unaffected\n"
        )

    try:
        verdicts = reconcile(
            args.slug,
            repo_root,
            args.base_ref,
            state_root=state_root,
            max_age_days=args.max_age_days,
        )
    except Exception as exc:  # noqa: BLE001 — reconcile errors must not crash a seam
        sys.stderr.write(f"reconcile_pipeline_state: {exc}\n")
        return 3

    if not verdicts:
        if not args.quiet:
            sys.stderr.write(f"reconcile_pipeline_state: no WIP.md for slug '{args.slug}'\n")
        return 3

    unnamed = unnamed_attempts(args.slug, state_root)
    if args.json:
        print(json.dumps(verdicts, indent=2))
    elif not args.quiet:
        print("\n".join(map(_readable_line, verdicts)))
    for text in unnamed:
        sys.stderr.write(f"reconcile_pipeline_state: WIP.md Attempts line names no step: {text}\n")

    return _exit_code(verdicts, unnamed)


if __name__ == "__main__":
    sys.exit(main())
