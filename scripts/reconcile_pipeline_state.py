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
blocked}. Tier-1 is always the arbiter: when correlation is ambiguous or the WAL
dropped a line, a step degrades to `unknown` (surfaced to the user) — never to a
guessed `verified-complete`. The WAL can only sharpen localization, never certify
work. `blocked` is an otherwise-done step the plan tags `mutation: on` whose
results carry no usable mutation reading.

Exit codes: 0 nothing to recover; 1 >=1 step needs recovery
(mismatch/partial/in-flight); 2 >=1 unknown or blocked (needs human); 3 reconcile
error.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from _repo_root import is_plugin_cache_path, resolve_repo_root
from _step_schema import (
    RecordedRun,
    checklist_step_id,
    mutation_block_reasons,
    parse_wip_claims,
    recorded_runs,
    step_id_from_heading,
    step_sort_key,
    step_test_status,
)
from _step_verdict import _classify_step

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

# A "**Files**:" field line under a plan step.
_FILES_FIELD_RE = re.compile(r"^\s*\*{0,2}Files\*{0,2}\s*:\s*(?P<files>.+)$", re.IGNORECASE)

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
) -> list[dict[str, Any]]:
    """Reconcile every step in ``.ai-work/<slug>/WIP.md`` against ground truth.

    Parameters mirror ``spec_drift.detect_drift``: ``repo_root`` is passed
    explicitly so the function works in any cwd (worktrees, tmp_path fixtures),
    and the ``_*_override`` hooks let tests inject the three external reads
    (git diff, the WAL, the test status) for hermetic, side-effect-free runs.

    ``state_root`` locates ``.ai-state/`` and ``.ai-work/`` when they live under
    a different root than the git repo (Standard-tier worktrees); it defaults to
    ``repo_root``.

    Returns one verdict dict per WIP step (see module docstring for the shape).
    Returns ``[]`` when there is no ``WIP.md`` for the slug (graceful degrade).
    """
    repo_root = Path(repo_root)
    state_root = Path(state_root) if state_root is not None else repo_root

    task_dir = state_root / ".ai-work" / slug
    wip_path = task_dir / "WIP.md"
    if not wip_path.exists():
        return []

    claims = _parse_wip_steps(wip_path)
    if not claims:
        return []

    plan_path = task_dir / "IMPLEMENTATION_PLAN.md"
    declared_files = _parse_plan_files(plan_path, wip_path)
    # The one read of the results file. `_test_status_override` (the test hook)
    # isolates the run from it entirely, so a hermetic run sees no results.
    results_text = (
        "" if _test_status_override is not None else _read_text(task_dir / "TEST_RESULTS.md")
    )
    mutation_blocks = mutation_block_reasons(
        _read_text(plan_path) or _read_text(wip_path), results_text
    )

    changed_files = (
        set(_changed_files_override)
        if _changed_files_override is not None
        else _git_changed_files(repo_root, base_ref)
    )
    # A per-step pool; empty under `_test_status_override`, which applies one
    # status to every step and so never consults it.
    test_runs = recorded_runs(results_text)
    wal_rows = (
        _wal_rows_override
        if _wal_rows_override is not None
        else _read_wal(reader.log_path(state_root / ".ai-state"), max_age_days=max_age_days)
    )

    return [
        _reconcile_step(
            step_id,
            claims[step_id],
            declared_files,
            changed_files,
            wal_rows,
            test_runs,
            _test_status_override,
            mutation_blocks.get(step_id),
        )
        for step_id in sorted(claims, key=step_sort_key)
    ]


def _reconcile_step(
    step_id: str,
    claim: str,
    declared_files: dict[str, list[str]],
    changed_files: set[str],
    wal_rows: list[dict[str, Any]],
    test_runs: list[RecordedRun],
    test_status_override: str | None,
    mutation_block: str | None,
) -> dict[str, Any]:
    # `attributable()` files only -- a file another step also declares isn't enough.
    files = attributable(step_id, declared_files)
    changed = [f for f in files if _path_in_changeset(f, changed_files)]
    return _classify_step(
        step_id=step_id,
        claim=claim,
        files=files,
        changed=changed,
        unchanged=[f for f in files if f not in changed],
        test_status=(
            test_status_override
            if test_status_override is not None
            else step_test_status(step_id, test_runs)
        ),
        tier2=_correlate_agents(files, wal_rows),
        earlier_declarers=_earlier_declarers(step_id, declared_files) if not files else [],
        mutation_block=mutation_block,
    )


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
    files = _scan_step_files(plan_path)
    if not files:
        files = _scan_step_files(wip_path)
    return files


def _scan_step_files(path: Path) -> dict[str, list[str]]:
    """Scan a plan/WIP doc: associate each ``**Files**:`` line with its step.

    A ``Files:`` field that wraps mid-value ends its line with a trailing
    comma; every further line ending in a comma continues the same logical
    value, so the admission predicate in ``_split_files`` sees the whole
    declaration rather than losing everything after the wrap.
    """
    lines = _read_text(path).splitlines()
    result: dict[str, list[str]] = {}
    current: str | None = None
    index = 0
    while index < len(lines):
        line = lines[index]
        step_id = step_id_from_heading(line) or checklist_step_id(line)
        if step_id is not None:
            current = step_id
            index += 1
            continue
        fm = _FILES_FIELD_RE.match(line)
        if fm and current:
            value, index = _collect_files_value(fm.group("files"), lines, index)
            result.setdefault(current, []).extend(_split_files(value))
            continue
        index += 1
    return result


def _collect_files_value(first: str, lines: list[str], index: int) -> tuple[str, int]:
    """Join a ``Files:`` value with its trailing-comma continuation lines,
    stopping at a step heading or checklist step line even when the current
    line still ends in a comma -- a plan heading always opens its own step.

    Returns the joined value and the index of the first line not consumed.
    """
    parts = [first]
    index += 1
    while parts[-1].rstrip().endswith(",") and index < len(lines):
        line = lines[index]
        if step_id_from_heading(line) is not None or checklist_step_id(line) is not None:
            break
        parts.append(line)
        index += 1
    return " ".join(parts), index


# A field value that, once leading markdown emphasis is stripped, declares no
# files at all.
_FILES_NONE_RE = re.compile(r"^(none|n/a)\b", re.IGNORECASE)
# A path-safe token — letters, digits, the punctuation a path or glob uses.
_FILE_CANDIDATE_RE = re.compile(r"^[A-Za-z0-9_./*?\[\]-]+$")
# A parenthetical span in a Files: value is rationale ("(see WIP.md)"), never
# a path — dropped before tokenizing so its contents can't be mistaken for one.
_RATIONALE_RE = re.compile(r"\([^)]*\)")


def _split_files(raw: str) -> list[str]:
    """Split a ``Files:`` field value into the individual paths it declares.

    A bare ``none``/``n/a`` — after stripping a bolded label's leading ``*``
    captured along with it — declares zero files. Otherwise: strip
    parenthetical rationale spans; tokenize on backtick-quoted spans when the
    value contains any backtick, else on commas/whitespace; admit a candidate
    only when it looks like a path — path-safe characters, a ``/`` or ``.``
    somewhere in it, no trailing ``/``, and no pointer into this pipeline's own
    ``.ai-work/`` bookkeeping (a step may legitimately cite its own artifacts
    as rationale, but that is not a file it changed).
    """
    value = raw.strip().lstrip("*").strip()
    if _FILES_NONE_RE.match(value):
        return []
    value = _RATIONALE_RE.sub(" ", value)
    tokens = re.findall(r"`([^`]+)`", value) if "`" in value else re.split(r"[,\s]+", value)
    candidates = (token.strip().strip("`").rstrip(".,;:") for token in tokens)
    return [c for c in candidates if c and _is_admitted_file(c)]


def _is_admitted_file(candidate: str) -> bool:
    return (
        bool(_FILE_CANDIDATE_RE.match(candidate))
        and ("/" in candidate or "." in candidate)
        and not candidate.endswith("/")
        and not candidate.startswith(".ai-work/")
    )


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


def _git_changed_files(repo_root: Path, base_ref: str | None) -> set[str]:
    """Repo-relative paths changed vs base_ref, plus the dirty working tree."""
    changed: set[str] = set()
    diff_targets = []
    if base_ref:
        diff_targets.append(["git", "diff", "--name-only", base_ref])
    diff_targets.append(["git", "diff", "--name-only", "HEAD"])  # unstaged + staged-vs-HEAD
    diff_targets.append(["git", "diff", "--name-only", "--cached"])  # staged
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


def _exit_code(verdicts: list[dict[str, Any]]) -> int:
    """0 clean; 1 recovery needed; 2 unknown or blocked present (a human decides)."""
    kinds = {v["verdict"] for v in verdicts}
    if kinds & {"unknown", "blocked"}:
        return 2
    if any(_needs_recovery(k) for k in kinds):
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile pipeline step-completion against ground truth (read-only)."
    )
    parser.add_argument("slug", help="task slug under .ai-work/<slug>/")
    parser.add_argument("--repo-root", default=None, help="git repo root (default: git rev-parse)")
    parser.add_argument(
        "--worktree-root",
        default=None,
        help="root holding .ai-state/ and .ai-work/ (default: --repo-root)",
    )
    parser.add_argument("--base-ref", default=None, help="git ref to diff against (e.g. main)")
    parser.add_argument("--json", action="store_true", help="emit verdict JSON array on stdout")
    parser.add_argument("--quiet", action="store_true", help="suppress the human summary")
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=7,
        help="max age in days of a log row; bounds every segment, active log included (default: 7)",
    )
    args = parser.parse_args(argv)

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

    if args.json:
        print(json.dumps(verdicts, indent=2))
    if not args.quiet and not args.json:
        for v in verdicts:
            print(f"{v['step']:>9}  {v['verdict']:<22}  {v['evidence']}")

    return _exit_code(verdicts)


if __name__ == "__main__":
    sys.exit(main())
