#!/usr/bin/env python3
"""Deterministic pipeline step-completion reconciler.

Answers "did this pipeline step actually complete?" from **ground truth**, not
from the agent-authored `WIP.md` checkbox. A subagent hard-truncated at its
context ceiling can finish real work but die before flipping its checkbox (or
leave a stale `[COMPLETE]` claim). This reader verifies each step's claim
against a three-tier reliability hierarchy and emits a per-step verdict that
`/resume-pipeline` consumes.

Reliability hierarchy (the spine):
  Tier 1 (arbiter)        — codebase + `git diff` + `TEST_RESULTS.md`.
  Tier 2 (localization)   — `.ai-state/observations.jsonl` (the harness WAL):
                            which agent stopped, where it last wrote. Only ever
                            *adds* a hint; never *overrides* a Tier-1 verdict.
  Tier 3 (never trusted)  — the `WIP.md` checkbox itself, validated here.

Entry point: ``reconcile(slug, repo_root, base_ref) -> list[verdict]`` is a pure,
side-effect-free function (no writes, no git mutation) — trivially unit-testable
via the ``_*_override`` hooks, and safe to run read-only at any pipeline seam.

Verdict ∈ {verified-complete, mismatch, partial, in-flight, unknown, pending}.
Tier-1 is always the arbiter: when correlation is ambiguous or the WAL dropped a
line, a step degrades to `unknown` (surfaced to the user) — never to a guessed
`verified-complete`. The WAL can only sharpen localization, never certify work.

Exit codes: 0 nothing to recover; 1 >=1 step needs recovery
(mismatch/partial/in-flight); 2 >=1 unknown (needs human); 3 reconcile error.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from _repo_root import is_plugin_cache_path, resolve_repo_root

SCRIPT_DIR = Path(__file__).resolve().parent

# Only step-executing agent types can be correlated to a WIP step verdict;
# research / doc / context agents touch files for other reasons.
STEP_EXECUTING_AGENT_TYPES = frozenset(
    {
        "i-am:implementer",
        "i-am:test-engineer",
        "i-am:implementation-planner",
        "implementer",
        "test-engineer",
        "implementation-planner",
    }
)

# WIP progress-line claim markers.
_COMPLETE_RE = re.compile(r"\[x\]|\[COMPLETE\]", re.IGNORECASE)
_IN_PROGRESS_RE = re.compile(r"\[IN-PROGRESS\]|\[IMPLEMENTING\]", re.IGNORECASE)
# A WIP progress entry: "- [x] Step 3 ...", "- [ ] Step 0 (test-engineer): ..."
_WIP_STEP_RE = re.compile(r"^\s*-\s*\[(?P<box>[ xX])\]\s*(?P<body>.*Step\s+(?P<num>\d+)\b.*)$")
# An IMPLEMENTATION_PLAN step header: "### Step 3: ..." (capture trailing text).
_PLAN_STEP_RE = re.compile(r"^#{2,4}\s*Step\s+(?P<num>\d+)\b\s*:?\s*(?P<rest>.*)$")
# A "**Files**:" field line under a plan step.
_FILES_FIELD_RE = re.compile(r"^\s*\*{0,2}Files\*{0,2}\s*:\s*(?P<files>.+)$", re.IGNORECASE)
# Pytest summary count tokens (word-boundary — never matches "ModuleNotFoundError").
_PYTEST_FAIL_RE = re.compile(r"\b(\d+)\s+(?:failed|errors?)\b", re.IGNORECASE)
_PYTEST_PASS_RE = re.compile(r"\b\d+\s+passed\b", re.IGNORECASE)


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

    declared_files = _parse_plan_files(task_dir / "IMPLEMENTATION_PLAN.md", wip_path)

    changed_files = (
        set(_changed_files_override)
        if _changed_files_override is not None
        else _git_changed_files(repo_root, base_ref)
    )
    test_status = (
        _test_status_override
        if _test_status_override is not None
        else _read_test_status(task_dir / "TEST_RESULTS.md")
    )
    wal_rows = (
        _wal_rows_override
        if _wal_rows_override is not None
        else _read_wal(
            state_root / ".ai-state" / "observations.jsonl",
            max_age_days=max_age_days,
        )
    )

    verdicts: list[dict[str, Any]] = []
    for step_id in sorted(claims, key=_step_sort_key):
        files = declared_files.get(step_id, [])
        tier2 = _correlate_agents(files, wal_rows)
        verdicts.append(
            _classify_step(
                step_id=step_id,
                claim=claims[step_id],
                files=files,
                changed_files=changed_files,
                test_status=test_status,
                tier2=tier2,
            )
        )
    return verdicts


# ---------------------------------------------------------------------------
# Classification — the verdict state machine
# ---------------------------------------------------------------------------


def _classify_step(
    *,
    step_id: str,
    claim: str,
    files: list[str],
    changed_files: set[str],
    test_status: str,
    tier2: dict[str, Any],
) -> dict[str, Any]:
    """Classify one step. Tier-1 (git + tests) is the arbiter — ground truth
    decides "done," NOT the WIP checkbox (which is Tier-3, validated here)."""
    changed = [f for f in files if _path_in_changeset(f, changed_files)]
    unchanged = [f for f in files if f not in changed]
    tier1 = {"files_changed": changed, "files_unchanged": unchanged, "tests": test_status}

    # No declared files → we cannot tie this step to specific ground truth.
    # Never guess `verified-complete`; degrade to a human-surfaced verdict.
    if not files:
        verdict = "unknown" if claim == "COMPLETE" else "pending"
        evidence = (
            "step declares no Files: and cannot be tied to git changes — "
            f"WIP claim={claim}; surfaced for human verification"
            if verdict == "unknown"
            else "step not started and declares no Files:"
        )
        return _make_verdict(step_id, claim, verdict, tier1, tier2, evidence, [])

    tests_red = test_status == "red"

    # Tier-1 arbiter: all declared files changed AND suite not red → the work IS
    # done, regardless of the checkbox. If the checkbox disagrees, it just needs
    # marking — the died-before-checkbox case the whole design targets.
    if changed and not unchanged and not tests_red:
        needs_mark = claim != "COMPLETE"
        evidence = f"all {len(changed)} declared file(s) changed; tests={test_status}" + (
            "; WIP not marked COMPLETE — auto-mark on resume" if needs_mark else ""
        )
        return _make_verdict(
            step_id, claim, "verified-complete", tier1, tier2, evidence, [], needs_mark=needs_mark
        )

    # Tier-1 does NOT confirm completion.
    if claim == "COMPLETE":
        # A [COMPLETE] claim ground truth contradicts — the truncation signature.
        scope = unchanged or files
        reason = (
            "tests red" if tests_red else f"{len(unchanged)} declared file(s) show no git change"
        )
        evidence = f"WIP=[COMPLETE] but {reason}: {', '.join(scope)}"
        return _make_verdict(step_id, claim, "mismatch", tier1, tier2, evidence, scope)

    # Honest not-complete claim — pending / partial / in-flight.
    return _classify_incomplete_claim(step_id, claim, tier1, tier2, changed, unchanged, files)


def _classify_incomplete_claim(
    step_id: str,
    claim: str,
    tier1: dict[str, Any],
    tier2: dict[str, Any],
    changed: list[str],
    unchanged: list[str],
    files: list[str],
) -> dict[str, Any]:
    """Classify a step whose claim is not COMPLETE and Tier-1 has not confirmed it:
    not-started (pending), stopped mid-work (partial), or still running (in-flight)."""
    if not changed:
        return _make_verdict(
            step_id, claim, "pending", tier1, tier2, "step not started (no file changes)", files
        )
    if tier2.get("agent_stop_seen"):
        last = tier2.get("last_write") or "?"
        evidence = (
            f"{len(changed)} file(s) changed; agent stopped after {last}; "
            f"remainder: {', '.join(unchanged)}"
        )
        return _make_verdict(step_id, claim, f"partial@{last}", tier1, tier2, evidence, unchanged)
    evidence = f"{len(changed)} file(s) changed, no terminal marker — possibly still running"
    return _make_verdict(step_id, claim, "in-flight", tier1, tier2, evidence, unchanged)


def _make_verdict(
    step_id: str,
    claim: str,
    verdict: str,
    tier1: dict[str, Any],
    tier2: dict[str, Any],
    evidence: str,
    resume_scope: list[str],
    *,
    needs_mark: bool = False,
) -> dict[str, Any]:
    """Construct a verdict dict satisfying the output contract.

    ``needs_mark`` is True for a ``verified-complete`` step whose checkbox was
    never flipped (the died-before-checkbox case) — the resume action is an
    auto-mark, not a re-spawn.
    """
    return {
        "step": step_id,
        "wip_claim": claim,
        "verdict": verdict,
        "needs_mark": needs_mark,
        "tier1": tier1,
        "tier2": tier2,
        "evidence": evidence,
        "resume_scope": resume_scope,
    }


# ---------------------------------------------------------------------------
# Tier-2 correlation — observations.jsonl WAL, file-containment first
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
    """Map ``Step N`` -> claim {COMPLETE, IN-PROGRESS, PENDING} from WIP.md."""
    try:
        content = wip_path.read_text(encoding="utf-8")
    except OSError:
        return {}
    claims: dict[str, str] = {}
    for line in content.splitlines():
        m = _WIP_STEP_RE.match(line)
        if not m:
            continue
        step_id = f"Step {m.group('num')}"
        body = m.group("body")
        if m.group("box").lower() == "x" or _COMPLETE_RE.search(body):
            claim = "COMPLETE"
        elif _IN_PROGRESS_RE.search(body):
            claim = "IN-PROGRESS"
        else:
            claim = "PENDING"
        prev = claims.get(step_id)
        if prev is None:
            claims[step_id] = claim
        elif prev != claim and prev != "AMBIGUOUS":
            # Same step number, conflicting claims (a multi-workstream WIP reuses
            # "Step N" per workstream). The checkbox cannot be trusted for this
            # number → mark AMBIGUOUS so Tier-1 ground truth alone decides; never
            # silently collapse to one workstream's claim.
            claims[step_id] = "AMBIGUOUS"
    return claims


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
    """Scan a plan/WIP doc: associate each ``**Files**:`` line with its step."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    result: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
        step = _PLAN_STEP_RE.match(line) or _WIP_STEP_RE.match(line)
        if step:
            current = f"Step {step.group('num')}"
            continue
        fm = _FILES_FIELD_RE.match(line)
        if fm and current:
            result.setdefault(current, []).extend(_split_files(fm.group("files")))
    return result


def _split_files(raw: str) -> list[str]:
    """Split a Files: field value into individual paths."""
    raw = raw.strip().strip("[]`")
    parts = re.split(r"[,\s]+", raw)
    return [
        p.strip().strip("`") for p in parts if p.strip() and "/" in p or p.strip().endswith(".py")
    ]


def _read_test_status(path: Path) -> str:
    """Test status from the FINAL pytest-style summary in TEST_RESULTS.md.

    Parses the LAST line that reads like a pytest summary (a count plus
    passed/failed/error), so an early failure block in a long accumulating file
    does not poison a suite that ended green. Coarse (global, not per-step — that
    attribution is future work), but the *final* state is the safe signal.
    `absent` does not block verified-complete (test-less steps are normal).
    """
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return "absent"
    # Match pytest *count* tokens with word boundaries, not bare substrings —
    # "ModuleNotFoundError"/"KeyError" in prose must not read as a failure.
    status = "absent"
    for line in content.splitlines():
        fail = _PYTEST_FAIL_RE.search(line)
        if fail and int(fail.group(1)) > 0:
            status = "red"  # a line reporting >=1 failure/error wins for that line
        elif _PYTEST_PASS_RE.search(line):
            status = "green"
    return status


def _parse_ts(ts: str) -> datetime:
    """Parse an ISO 8601 timestamp; return the epoch on parse error.

    Epoch acts as "infinitely old" so malformed timestamps in the .1 segment
    are pruned by the window filter.  Active-file rows never reach this helper.
    """
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except (ValueError, TypeError):
        return datetime.fromtimestamp(0, UTC)


def _parse_jsonl(path: Path) -> list[dict[str, Any]]:
    """Parse a JSONL file into a list of dicts; tolerate partial lines and OSError."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # a truncated final line never corrupts the read
    return rows


def _read_wal(
    obs_path: Path,
    *,
    max_age_days: int = 7,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Read observations.jsonl (active) + optional rotated .1 segment within a window.

    Active-file rows are retained unconditionally — the active file is
    size-bounded by rotation, so a current-session row with a malformed/missing
    timestamp must still reach correlation (pre-mortem scenario 6).

    The .1 segment is included only when its mtime falls within max_age_days,
    and its rows are additionally timestamp-filtered to the same window.
    Malformed timestamps in the segment parse as epoch → outside any window → pruned.
    """
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=max_age_days)

    active_rows = _parse_jsonl(obs_path)

    seg_path = Path(str(obs_path) + ".1")
    seg_rows: list[dict[str, Any]] = []
    try:
        seg_mtime = datetime.fromtimestamp(seg_path.stat().st_mtime, UTC)
        if seg_mtime >= cutoff:
            seg_rows = [
                r for r in _parse_jsonl(seg_path) if _parse_ts(r.get("timestamp", "")) >= cutoff
            ]
    except OSError:
        pass  # segment absent or unreadable → skip silently

    return active_rows + seg_rows


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
        return (
            fnmatch.fnmatch(c, d)
            or fnmatch.fnmatch(c, "*/" + d)
            or fnmatch.fnmatch(Path(c).name, Path(d).name)
        )
    return (
        c == d
        or c.endswith("/" + d)
        or d.endswith("/" + c)
        or (Path(c).name == Path(d).name and d in c)
    )


def _path_in_changeset(declared: str, changed_files: set[str]) -> bool:
    """True if a declared file appears in the git changeset (suffix-aware)."""
    return any(_path_match(declared, c) for c in changed_files)


def _step_sort_key(step_id: str) -> tuple[int, str]:
    """Sort 'Step N' numerically."""
    m = re.search(r"(\d+)", step_id)
    return (int(m.group(1)) if m else 0, step_id)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

_RECOVERY_VERDICTS = ("mismatch", "in-flight")


def _needs_recovery(verdict: str) -> bool:
    return verdict in _RECOVERY_VERDICTS or verdict.startswith("partial")


def _exit_code(verdicts: list[dict[str, Any]]) -> int:
    """0 clean; 1 recovery needed; 2 unknown present."""
    kinds = {v["verdict"] for v in verdicts}
    if any(k == "unknown" for k in kinds):
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
        help="max age in days for the rotated WAL segment (default: 7)",
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
