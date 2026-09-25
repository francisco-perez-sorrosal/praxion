"""Tests for reconcile_pipeline_state — verdict state machine + gate-liveness canary.

Hermetic: the three external reads (git diff, the WAL, the test status) are
injected via reconcile()'s ``_*_override`` hooks, so no real git repo is needed.
WIP.md / IMPLEMENTATION_PLAN.md are written into a tmp_path .ai-work/<slug>/ dir.

Run: ``python3 scripts/test_reconcile_pipeline_state.py`` or ``pytest``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import mutation_sensor as ms  # noqa: E402
import reconcile_pipeline_state as rps  # noqa: E402

SLUG = "demo-task"


def _setup(tmp_path: Path, wip: str, plan: str | None = None) -> Path:
    """Create .ai-work/<slug>/{WIP,IMPLEMENTATION_PLAN}.md under tmp_path."""
    task_dir = tmp_path / ".ai-work" / SLUG
    task_dir.mkdir(parents=True)
    (task_dir / "WIP.md").write_text(wip, encoding="utf-8")
    if plan is not None:
        (task_dir / "IMPLEMENTATION_PLAN.md").write_text(plan, encoding="utf-8")
    return tmp_path


def _verdict_for(verdicts: list[dict], step: str) -> dict:
    return next(v for v in verdicts if v["step"] == step)


def _wal_write(agent_id: str, agent_type: str, path: str, ts: str) -> dict:
    return {
        "event_type": "tool_use",
        "agent_id": agent_id,
        "agent_type": agent_type,
        "file_paths": [path],
        "timestamp": ts,
    }


def _wal_stop(agent_id: str) -> dict:
    return {"event_type": "agent_stop", "agent_id": agent_id}


PLAN_ONE_STEP = """## Steps

### Step 1: Build the thing
**Assignee**: implementer
**Files**: src/foo.py
**Done when**: it works
"""

PLAN_TWO_FILES = """### Step 1: Build the thing
**Files**: src/a.py, src/b.py
"""


# --- genuine completion confirmed from ground truth ------------------------


def test_verified_complete_when_files_changed_and_tests_green(tmp_path):
    root = _setup(tmp_path, "- [x] Step 1: build\n", PLAN_ONE_STEP)
    out = rps.reconcile(
        SLUG,
        root,
        None,
        _changed_files_override=["src/foo.py"],
        _wal_rows_override=[],
        _test_status_override="green",
    )
    assert _verdict_for(out, "Step 1")["verdict"] == "verified-complete"


# --- THE CANARY — a false [COMPLETE] must be flagged ------------------------


def test_canary_complete_but_files_unchanged_is_flagged(tmp_path):
    """GATE-LIVENESS CANARY (golden bad-case).

    A step claims [COMPLETE] but its Files show zero git change — the exact
    truncation signature. The reconciler MUST NOT return verified-complete.

    Proof it bites (mutation-verified): replace _classify_step's
    verified-complete guard condition `changed and not unchanged and not
    tests_red` with an unconditional `if True:` (i.e. trust the checkbox), and
    this test goes red — the false [COMPLETE] claim then returns
    verified-complete. (Mutating only the `not unchanged` term does NOT bite,
    because `changed` is already empty here.)
    """
    root = _setup(tmp_path, "- [x] Step 1: build\n", PLAN_ONE_STEP)
    out = rps.reconcile(
        SLUG,
        root,
        None,
        _changed_files_override=[],  # nothing changed in git
        _wal_rows_override=[],
        _test_status_override="green",
    )
    v = _verdict_for(out, "Step 1")
    assert v["verdict"] != "verified-complete"
    assert v["verdict"] == "mismatch"
    assert "src/foo.py" in v["resume_scope"]


def test_canary_red_tests_block_verified_complete(tmp_path):
    """A [COMPLETE] step whose files changed but suite is red → mismatch."""
    root = _setup(tmp_path, "- [x] Step 1: build\n", PLAN_ONE_STEP)
    out = rps.reconcile(
        SLUG,
        root,
        None,
        _changed_files_override=["src/foo.py"],
        _wal_rows_override=[],
        _test_status_override="red",
    )
    assert _verdict_for(out, "Step 1")["verdict"] == "mismatch"


# --- partial localizes to the last write -----------------------------------


def test_partial_localizes_remainder(tmp_path):
    root = _setup(tmp_path, "- [ ] Step 1: build\n", PLAN_TWO_FILES)
    out = rps.reconcile(
        SLUG,
        root,
        None,
        _changed_files_override=["src/a.py"],  # a done, b not
        _wal_rows_override=[
            _wal_write("ag1", "praxion:implementer", "/repo/src/a.py", "2026-06-22T19:00:00Z"),
            _wal_stop("ag1"),
        ],
        _test_status_override="green",
    )
    v = _verdict_for(out, "Step 1")
    assert v["verdict"].startswith("partial@")
    assert v["resume_scope"] == ["src/b.py"]
    assert v["tier2"]["agent_stop_seen"] is True


# --- Tier-1 overrides Tier-2 loss (dropped WAL lines) ----------------------


def test_tier1_overrides_wal_loss(tmp_path):
    """Files changed + tests green, but the WAL has no matching rows → still
    verified-complete. A dropped WAL line costs a hint, never a Tier-1 verdict."""
    root = _setup(tmp_path, "- [x] Step 1: build\n", PLAN_ONE_STEP)
    out = rps.reconcile(
        SLUG,
        root,
        None,
        _changed_files_override=["src/foo.py"],
        _wal_rows_override=[],  # WAL dropped everything
        _test_status_override="green",
    )
    v = _verdict_for(out, "Step 1")
    assert v["verdict"] == "verified-complete"
    assert v["tier2"]["correlated_agent_ids"] == []


# --- ambiguous correlation (no declared Files) degrades to unknown ---------


def test_complete_without_declared_files_is_unknown(tmp_path):
    """A [COMPLETE] step with no Files: cannot be tied to ground truth → unknown,
    never a guessed verified-complete."""
    root = _setup(tmp_path, "- [x] Step 1: build\n")  # no plan, no Files
    out = rps.reconcile(
        SLUG,
        root,
        None,
        _changed_files_override=["src/something.py"],
        _wal_rows_override=[],
        _test_status_override="green",
    )
    assert _verdict_for(out, "Step 1")["verdict"] == "unknown"


# --- in-flight and pending ----------------------------------------------------


def test_in_flight_when_changed_but_no_stop(tmp_path):
    root = _setup(tmp_path, "- [ ] Step 1: build\n", PLAN_TWO_FILES)
    out = rps.reconcile(
        SLUG,
        root,
        None,
        _changed_files_override=["src/a.py"],
        _wal_rows_override=[
            _wal_write("ag1", "praxion:implementer", "/repo/src/a.py", "2026-06-22T19:00:00Z"),
        ],  # tool_use but NO agent_stop
        _test_status_override="absent",
    )
    assert _verdict_for(out, "Step 1")["verdict"] == "in-flight"


def test_pending_when_nothing_changed(tmp_path):
    root = _setup(tmp_path, "- [ ] Step 1: build\n", PLAN_TWO_FILES)
    out = rps.reconcile(
        SLUG,
        root,
        None,
        _changed_files_override=[],
        _wal_rows_override=[],
        _test_status_override="absent",
    )
    assert _verdict_for(out, "Step 1")["verdict"] == "pending"


# --- read-only — reconcile() mutates nothing -------------------------------


def test_reconcile_is_side_effect_free(tmp_path):
    root = _setup(tmp_path, "- [x] Step 1: build\n", PLAN_ONE_STEP)
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    rps.reconcile(
        SLUG,
        root,
        None,
        _changed_files_override=["src/foo.py"],
        _wal_rows_override=[],
        _test_status_override="green",
    )
    after = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert before == after, "reconcile() must not write or modify any file"


# --- exit-code precedence ----------------------------------------------------


def test_exit_codes():
    assert rps._exit_code([{"verdict": "verified-complete"}]) == 0
    assert rps._exit_code([{"verdict": "pending"}]) == 0
    assert rps._exit_code([{"verdict": "mismatch"}]) == 1
    assert rps._exit_code([{"verdict": "partial@src/x.py"}]) == 1
    assert rps._exit_code([{"verdict": "in-flight"}]) == 1
    assert rps._exit_code([{"verdict": "unknown"}]) == 2
    # unknown outranks recovery-needed
    assert rps._exit_code([{"verdict": "mismatch"}, {"verdict": "unknown"}]) == 2


# --- parsing helpers ----------------------------------------------------------


def test_parse_wip_claims(tmp_path):
    wip = (
        "- [x] Step 1: done **[COMPLETE]**\n"
        "- [ ] Step 2: pending\n"
        "- [ ] Step 3 (implementer) [IN-PROGRESS]: working\n"
    )
    p = tmp_path / "WIP.md"
    p.write_text(wip, encoding="utf-8")
    claims = rps._parse_wip_steps(p)
    assert claims == {"Step 1": "COMPLETE", "Step 2": "PENDING", "Step 3": "IN-PROGRESS"}


def test_scan_step_files(tmp_path):
    p = tmp_path / "IMPLEMENTATION_PLAN.md"
    p.write_text(PLAN_TWO_FILES, encoding="utf-8")
    assert rps._scan_step_files(p) == {"Step 1": ["src/a.py", "src/b.py"]}


def test_missing_wip_returns_empty(tmp_path):
    assert rps.reconcile("nonexistent", tmp_path, None, _changed_files_override=[]) == []


def test_path_match_boundary_aware():
    assert rps._path_match("src/foo.py", "/repo/src/foo.py")
    assert rps._path_match("src/foo.py", "src/foo.py")
    assert not rps._path_match("src/foo.py", "/repo/other/bar.py")


def test_path_match_expands_globs():
    # git emits concrete paths; a glob in Files: must still match (no false mismatch)
    assert rps._path_match("scenarios/*.yaml", "pkg/scenarios/foo.yaml")
    assert rps._path_match("src/evals/scenarios/*.yaml", "src/evals/scenarios/contradiction.yaml")
    assert not rps._path_match("scenarios/*.yaml", "pkg/other/foo.py")


# --- ground truth drives verified-complete, not the checkbox ------------------


def test_verified_complete_overrides_unmarked_checkbox(tmp_path):
    """Died-before-checkbox: files all changed + tests green but WIP still '- [ ]'
    → verified-complete with needs_mark=True (resume auto-marks, does not respawn)."""
    root = _setup(tmp_path, "- [ ] Step 1: build\n", PLAN_ONE_STEP)
    out = rps.reconcile(
        SLUG,
        root,
        None,
        _changed_files_override=["src/foo.py"],
        _wal_rows_override=[_wal_stop("ag1")],
        _test_status_override="green",
    )
    v = _verdict_for(out, "Step 1")
    assert v["verdict"] == "verified-complete"
    assert v["needs_mark"] is True


# --- Bug B: conflicting step claims across workstreams → AMBIGUOUS -------------


def test_conflicting_wip_claims_mark_ambiguous(tmp_path):
    wip = (
        "## WS-1\n- [x] Step 1: done in ws1 **[COMPLETE]**\n"
        "## WS-2\n- [ ] Step 1: not done in ws2\n"
    )
    p = tmp_path / "WIP.md"
    p.write_text(wip, encoding="utf-8")
    claims = rps._parse_wip_steps(p)
    assert claims["Step 1"] == "AMBIGUOUS"


def test_ambiguous_claim_never_false_mismatch(tmp_path):
    """An AMBIGUOUS step with no confirming git change degrades safely, never to
    a mismatch (which would wrongly auto-resume)."""
    wip = "## WS-1\n- [x] Step 1 **[COMPLETE]**\n## WS-2\n- [ ] Step 1\n"
    root = _setup(tmp_path, wip, PLAN_ONE_STEP)
    out = rps.reconcile(
        SLUG,
        root,
        None,
        _changed_files_override=[],
        _wal_rows_override=[],
        _test_status_override="green",
    )
    assert _verdict_for(out, "Step 1")["verdict"] != "mismatch"


# --- Bug A: a step with no own run falls back to the file's latest run -----
#
# A step with no recorded run of its own takes the file's latest run, so these
# cases drive that fallback branch directly:
# `step_test_status(<a step absent from the file>, recorded_runs(text))`.


def _fallback_status(text: str) -> str:
    """The file's overall latest recorded run, via the production fallback
    path for a step with no own run of its own -- the direct replacement for
    the deleted whole-file reader."""
    return rps.step_test_status("__no_such_step__", rps.recorded_runs(text))


def test_test_status_uses_final_summary():
    text = (
        "## Step 1\nEarly iteration: 3 failed, 50 passed\n"
        "## Step 2\nFinal run: 3579 passed, 2 skipped in 12.3s\n"
    )
    assert _fallback_status(text) == "green"


def test_test_status_red_when_final_run_fails():
    text = "All passed earlier: 100 passed\nThen: 2 failed, 98 passed\n"
    assert _fallback_status(text) == "red"


def test_test_status_green_for_fixed_shape_result_line():
    """A file in the canonical per-step shape (dec-386) whose last section's
    ``Result:`` line reports fail=0 reads as green."""
    text = (
        "## Step 1\n"  # id-citation-discipline:ignore
        "Command: `uv run pytest -q`\n"
        "Result: pass=12 fail=0 skip=0\n"
        "Duration: 0.5s\n"
    )
    assert _fallback_status(text) == "green"


def test_test_status_red_for_fixed_shape_result_line_with_failures():
    """A fixed-shape Result: line with fail=2 reads as red for that line."""
    text = (
        "## Step 1\n"  # id-citation-discipline:ignore
        "Command: `uv run pytest -q`\n"
        "Result: pass=10 fail=2 skip=0\n"
        "Duration: 0.5s\n"
    )
    assert _fallback_status(text) == "red"


def test_test_status_mixed_shapes_last_fixed_shape_section_wins():
    """A pytest-style red line followed by a later fixed-shape green section —
    last line wins overall, across shapes."""
    text = (
        "## Step 1\n"  # id-citation-discipline:ignore
        "Early iteration: 3 failed, 50 passed\n"
        "## Step 2\n"  # id-citation-discipline:ignore
        "Result: pass=53 fail=0 skip=0\n"
    )
    assert _fallback_status(text) == "green"


def test_test_status_prose_summary_then_fixed_shape_green_wins():
    """A prose line resembling a pytest summary, followed by a fixed-shape
    green section, reads as green — the fixed-shape line is authoritative."""
    text = (
        "Historical note: 11 passed / 1 failed in an earlier run\n"
        "## Step 1\n"  # id-citation-discipline:ignore
        "Result: pass=11 fail=0 skip=0\n"
    )
    assert _fallback_status(text) == "green"


def test_test_status_red_for_fixed_shape_all_zero_result_line():
    """A fixed-shape Result: line with pass=0 fail=0 skip=0 is a pytest collection
    error (e.g. ModuleNotFoundError above a ### Failures block) rendering exactly
    that all-zero shape — it must read red, never green, since nothing was proven."""
    text = (
        "## Step 1\n"  # id-citation-discipline:ignore
        "Command: `uv run pytest -q`\n"
        "Result: pass=0 fail=0 skip=0\n"
        "Duration: 0.1s\n"
        "### Failures\n"
        "ModuleNotFoundError: No module named 'missing_thing'\n"
    )
    assert _fallback_status(text) == "red"


def test_test_status_all_zero_section_then_green_section_last_wins():
    """An all-zero (collection error) fixed-shape section followed by a later
    green fixed-shape section — last line wins, so the file reads green."""
    text = (
        "## Step 1\n"  # id-citation-discipline:ignore
        "Result: pass=0 fail=0 skip=0\n"
        "## Step 2\n"  # id-citation-discipline:ignore
        "Result: pass=5 fail=0 skip=0\n"
    )
    assert _fallback_status(text) == "green"


# --- backward compatibility: the optional `Mutation:` step-section line -----
#
# Both fixture lines are built by calling the shipped scripts/mutation_sensor.py
# directly (imported below) rather than hand-copied strings, so a future
# change to the runner's exact rendering re-derives the fixture instead of
# silently drifting from it.


def _mutation_survivors_line_at_cap() -> str:
    """The real `survivors=` rendering, sized so it lands exactly at the
    runner's 240-byte hard cap -- the boundary where a regression could
    silently push a green section's byte count somewhere unexpected."""
    per_function = {
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": 19,
        "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb": 9,
        "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc": 8,
        "d": 4,
        "e": 4,
        "f": 3,
        "g": 2,
    }
    histogram = {
        "killed": 0,
        "survived": sum(per_function.values()),
        "no_tests": 0,
        "skipped": 0,
        "suspicious": 0,
        "timeout": 0,
        "segfault": 0,
    }
    outcome = ms.Ran(
        targets=("a.py",),
        mutants=sum(per_function.values()),
        histogram=histogram,
        per_function=per_function,
        elapsed_s=1.0,
    )
    line = ms.render_line(outcome)
    assert len(line.encode("utf-8")) == ms.LINE_BYTE_CAP, (
        f"fixture drifted off the byte cap: {len(line.encode('utf-8'))} bytes, "
        f"expected exactly {ms.LINE_BYTE_CAP}"
    )
    return line


def _mutation_unavailable_line() -> str:
    """The real `unavailable` refusal rendering, built the same way the
    runner's own `_emit` renders a `toolchain-missing` refusal."""
    reason = ms.ReasonCode.TOOLCHAIN_MISSING.value
    detail = ms._one_line("uv not found on PATH")
    return f"Mutation: unavailable reason={reason} ({detail})"


def test_test_status_green_with_mutation_survivors_line_matches_shape_without_it():
    """A green fixed-shape section carrying the `survivors=` line at exactly
    its byte cap classifies exactly as it would without the line -- green."""
    text = (
        "## Step 1\n"  # id-citation-discipline:ignore
        "Command: `uv run pytest -q`\n"
        "Result: pass=12 fail=0 skip=0\n"
        "Duration: 0.5s\n"
        f"{_mutation_survivors_line_at_cap()}\n"
    )
    assert _fallback_status(text) == "green"


def test_test_status_green_with_mutation_unavailable_line_matches_shape_without_it():
    """A green fixed-shape section carrying the `unavailable` refusal line
    classifies exactly as it would without the line -- green. A legitimate
    refusal must never read as a failure."""
    text = (
        "## Step 1\n"  # id-citation-discipline:ignore
        "Command: `uv run pytest -q`\n"
        "Result: pass=12 fail=0 skip=0\n"
        "Duration: 0.5s\n"
        f"{_mutation_unavailable_line()}\n"
    )
    assert _fallback_status(text) == "green"


def test_test_status_red_result_line_wins_regardless_of_mutation_line():
    """Canary: a red Result: line (fail > 0) still classifies red even when a
    Mutation: line is present -- the line must never launder a real failure
    into green, whichever of the two shapes it carries. `survivors=3` and
    `(fn: 2)` must never be read as a passing count by the pytest-count
    regexes this reader also scans for."""
    text = (
        "## Step 1\n"  # id-citation-discipline:ignore
        "Command: `uv run pytest -q`\n"
        "Result: pass=10 fail=2 skip=0\n"
        "Duration: 0.5s\n"
        f"{_mutation_survivors_line_at_cap()}\n"
    )
    assert _fallback_status(text) == "red"


# --- windowed WAL read + cross-boundary recovery (Step 5 / Group B) ----------
#
# These tests call _read_wal(obs_path, max_age_days=7, now=<datetime>) — the
# new windowed signature that does NOT yet exist. All 6 are expected RED until
# the implementer's Step 4 lands the 2-file windowed _read_wal.
#
# RED trigger: TypeError — _read_wal() got an unexpected keyword argument 'now'
#
# Scenario 6 (WIP.md pre-mortem): active-file rows are retained unconditionally;
# only the .1 segment is mtime/timestamp-pruned. A malformed-timestamp row in
# the active file must never be dropped. _keeps_active_row_with_malformed_timestamp
# guards this contract.


_NOW = datetime(2026, 6, 26, 12, 0, 0, tzinfo=timezone.utc)
_WITHIN_WINDOW_TS = "2026-06-25T12:00:00+00:00"  # 1 day before _NOW
_OUTSIDE_WINDOW_TS = "2026-06-10T12:00:00+00:00"  # 16 days before _NOW


def test_cross_boundary_canary_reconciler_sees_events_split_across_rotation(tmp_path):
    """Load-bearing canary: agent_start+tool_use in .1, agent_stop in active —
    _read_wal must return all 3 rows AND _correlate_agents must see the stop."""
    obs_path = tmp_path / "observations.jsonl"
    seg_path = tmp_path / "observations.jsonl.1"

    declared_file = "src/cross_boundary_feature.py"

    # Two rows written to the rotated segment (.1) — the "old session"
    seg_rows = [
        {
            "event_type": "agent_start",
            "agent_id": "agent-A",
            "agent_type": "praxion:implementer",
            "timestamp": _WITHIN_WINDOW_TS,
        },
        {
            "event_type": "tool_use",
            "agent_id": "agent-A",
            "agent_type": "praxion:implementer",
            "file_paths": [f"/repo/{declared_file}"],
            "timestamp": _WITHIN_WINDOW_TS,
        },
    ]
    seg_path.write_text("\n".join(json.dumps(r) for r in seg_rows) + "\n", encoding="utf-8")

    # One row in the active file — the stop that arrived after rotation
    stop_row = {
        "event_type": "agent_stop",
        "agent_id": "agent-A",
        "timestamp": _WITHIN_WINDOW_TS,
    }
    obs_path.write_text(json.dumps(stop_row) + "\n", encoding="utf-8")

    # Windowed 2-file read must return all 3 rows (2 from .1 + 1 from active)
    rows = rps._read_wal(obs_path, max_age_days=7, now=_NOW)
    assert len(rows) == 3, f"expected 3 rows across boundary, got {len(rows)}"

    # Correlation must surface the agent_stop even though it lived in the active file
    tier2 = rps._correlate_agents([declared_file], rows)
    assert tier2["agent_stop_seen"] is True, (
        "agent_stop in active file must be visible after 2-file stitch"
    )


def test_read_wal_excludes_rows_older_than_window(tmp_path):
    """Rows with timestamps older than max_age_days in the .1 segment are pruned."""
    obs_path = tmp_path / "observations.jsonl"
    seg_path = tmp_path / "observations.jsonl.1"

    stale_row = {"event_type": "tool_use", "agent_id": "stale", "timestamp": _OUTSIDE_WINDOW_TS}
    seg_path.write_text(json.dumps(stale_row) + "\n", encoding="utf-8")
    obs_path.write_text("", encoding="utf-8")

    rows = rps._read_wal(obs_path, max_age_days=7, now=_NOW)
    assert len(rows) == 0, "stale segment row must be excluded from the windowed read"


def test_read_wal_skips_segment_when_mtime_out_of_window(tmp_path):
    """When .1 mtime is older than max_age_days, the segment is not read at all."""
    obs_path = tmp_path / "observations.jsonl"
    seg_path = tmp_path / "observations.jsonl.1"

    # Segment has a row with a recent-looking timestamp but the FILE is old
    recent_looking_row = {"event_type": "tool_use", "timestamp": _WITHIN_WINDOW_TS}
    seg_path.write_text(json.dumps(recent_looking_row) + "\n", encoding="utf-8")

    # Set mtime to 10 days before _NOW — outside the 7-day window
    old_mtime = (_NOW - timedelta(days=10)).timestamp()
    os.utime(seg_path, (old_mtime, old_mtime))

    obs_path.write_text("", encoding="utf-8")

    rows = rps._read_wal(obs_path, max_age_days=7, now=_NOW)
    assert len(rows) == 0, "segment with out-of-window mtime must be skipped entirely"


def test_read_wal_handles_missing_segment_gracefully(tmp_path):
    """When .1 is absent, _read_wal returns active rows without error."""
    obs_path = tmp_path / "observations.jsonl"
    # No seg_path created — .1 does not exist

    active_row = {"event_type": "agent_stop", "agent_id": "agent-B", "timestamp": _WITHIN_WINDOW_TS}
    obs_path.write_text(json.dumps(active_row) + "\n", encoding="utf-8")

    rows = rps._read_wal(obs_path, max_age_days=7, now=_NOW)
    assert len(rows) == 1
    assert rows[0]["event_type"] == "agent_stop"


def test_canary_single_file_read_misses_current_session_events_after_rotation(tmp_path):
    """Gate-liveness canary: when active file is empty and .1 holds recent rows,
    _read_wal must return the .1 rows — proving 2-file read is required.

    If _read_wal read only the active file (the pre-Step-4 behaviour), this
    assertion would fail (0 rows returned) — the regression this canary catches.
    """
    obs_path = tmp_path / "observations.jsonl"
    seg_path = tmp_path / "observations.jsonl.1"

    # Post-rotation state: fresh empty active + prior session events in .1
    obs_path.write_text("", encoding="utf-8")
    seg_row = {
        "event_type": "tool_use",
        "agent_id": "agent-C",
        "agent_type": "praxion:implementer",
        "timestamp": _WITHIN_WINDOW_TS,
    }
    seg_path.write_text(json.dumps(seg_row) + "\n", encoding="utf-8")

    rows = rps._read_wal(obs_path, max_age_days=7, now=_NOW)
    assert len(rows) == 1, "post-rotation .1 rows must be returned by the 2-file windowed read"
    assert rows[0]["agent_id"] == "agent-C"


def test_read_wal_keeps_active_row_with_malformed_timestamp(tmp_path):
    """Active-file rows with missing or garbage timestamps are retained unconditionally.

    Contrast: an equivalently malformed timestamp in the .1 segment is pruned
    (malformed timestamp parses as epoch → epoch is outside any reasonable window).
    This guards the pre-mortem scenario 6 correctness refinement: recovery errs
    toward inclusion; a bad correlation degrades to unknown→user, never a false verdict.
    """
    obs_path = tmp_path / "observations.jsonl"
    seg_path = tmp_path / "observations.jsonl.1"

    # Active file: row with garbage timestamp — must be retained
    malformed_active = {
        "event_type": "tool_use",
        "agent_id": "agent-D",
        "timestamp": "NOT_A_TIMESTAMP",
    }
    obs_path.write_text(json.dumps(malformed_active) + "\n", encoding="utf-8")

    # Segment: row with same garbage timestamp — must be pruned (epoch → old → outside window)
    malformed_seg = {
        "event_type": "tool_use",
        "agent_id": "agent-E",
        "timestamp": "NOT_A_TIMESTAMP",
    }
    seg_path.write_text(json.dumps(malformed_seg) + "\n", encoding="utf-8")

    rows = rps._read_wal(obs_path, max_age_days=7, now=_NOW)

    agent_ids_returned = {r.get("agent_id") for r in rows}
    assert "agent-D" in agent_ids_returned, (
        "active-file row with malformed timestamp must be retained unconditionally"
    )
    assert "agent-E" not in agent_ids_returned, (
        "segment row with malformed timestamp must be pruned (parsed as epoch → outside window)"
    )


# --- graceful degradation on a fully absent raw WAL (fresh clone, since the raw
# WAL left git tracking) -----------------------------------------------------


def test_read_wal_handles_missing_active_file_gracefully(tmp_path):
    """No observations.jsonl at all (not even an empty one) must not raise.

    This is the fresh-clone scenario every future clone hits once the raw WAL
    left git tracking: the file is absent, not empty.
    """
    obs_path = tmp_path / "observations.jsonl"  # never created

    rows = rps._read_wal(obs_path, max_age_days=7, now=_NOW)
    assert rows == []


def test_reconcile_ignores_absent_wal_and_trusts_tier1(tmp_path):
    """reconcile() with a real (absent) .ai-state/observations.jsonl must still
    classify from Tier-1 (files changed + tests) — Tier-2 correlation degrades
    to empty, it never blocks or corrupts the Tier-1 verdict."""
    root = _setup(tmp_path, "- [ ] Step 1: build\n", PLAN_ONE_STEP)
    # No .ai-state/ directory at all — the real absent-WAL shape, not an override.
    out = rps.reconcile(
        SLUG,
        root,
        None,
        _changed_files_override=["src/foo.py"],
        _test_status_override="green",
    )
    verdict = _verdict_for(out, "Step 1")
    assert verdict["verdict"] == "verified-complete"
    assert verdict["tier2"]["agent_stop_seen"] is False


def test_main_reports_no_local_wal_on_stderr_when_absent(tmp_path, capsys, monkeypatch):
    """main() surfaces an explicit INFO line when the raw WAL is absent —
    Tier-1 classification proceeds unaffected (no traceback, no crash)."""
    _setup(tmp_path, "- [x] Step 1: build\n", PLAN_ONE_STEP)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(rps, "resolve_repo_root", lambda *_a, **_k: tmp_path)
    monkeypatch.setattr(rps, "is_plugin_cache_path", lambda *_a, **_k: False)
    monkeypatch.setattr(rps, "_git_changed_files", lambda *_a, **_k: {"src/foo.py"})

    exit_code = rps.main([SLUG, "--json"])
    err = capsys.readouterr().err
    assert "no local WAL" in err
    assert exit_code == 0


# --- Files: field admission ignores a trailing parenthetical rationale ------


def test_split_files_admits_only_the_declared_path_when_followed_by_a_parenthetical_rationale():
    """A rationale in parentheses naming an unrelated document must never be
    read as a second declared file, and the rationale's own trailing token
    must never survive as a bare fragment either."""
    assert rps._split_files("scripts/a.py (see .ai-work/x/WIP.md, n/a)") == ["scripts/a.py"]


def test_split_files_recognizes_a_bare_none_declaration_with_stray_leading_emphasis():
    """A ``**Files:** none`` field renders its captured value with a leading
    ``**`` still attached to the token -- the none/n-a check must strip
    markdown emphasis before testing, not only surrounding whitespace."""
    assert rps._split_files("** none") == []


def test_split_files_admits_backtick_quoted_comma_separated_paths():
    assert rps._split_files("`src/a.py`, `src/b.py`") == ["src/a.py", "src/b.py"]


def test_split_files_admits_bare_comma_separated_paths():
    assert rps._split_files("src/a.py, src/b.py") == ["src/a.py", "src/b.py"]


def test_split_files_does_not_admit_an_extensionless_top_level_name():
    """Declared limit: a bare top-level filename with no directory separator
    and no extension (e.g. ``Makefile``) is never treated as a declared file."""
    assert rps._split_files("Makefile") == []


# --- a wrapped Files: field keeps every trailing-comma continuation line ----
#
# Verbatim excerpt of a real harvested plan's Files: field -- roughly 38 of
# 296 real fields wrap this way, and every continuation line must be gathered
# before the admission predicate runs, not just the opening line.

_P3_5_WRAPPED_FILES_FIELD = (
    "**Files**: `scripts/project_metrics/tests/test_cost_collector.py`,\n"
    "`scripts/project_metrics/tests/fixtures/cost/attributed.jsonl`,\n"
    "`scripts/project_metrics/tests/fixtures/cost/pre_attribution.jsonl`,\n"
    "`scripts/project_metrics/tests/fixtures/cost/unparsed.jsonl`,\n"
    "`scripts/project_metrics/tests/fixtures/cost/parent_sourced_synthetic.jsonl`\n"
)


def test_scan_step_files_keeps_every_line_of_a_wrapped_trailing_comma_continuation(tmp_path):
    plan_path = tmp_path / "IMPLEMENTATION_PLAN.md"
    plan_path.write_text("### Step 1: RED\n" + _P3_5_WRAPPED_FILES_FIELD, encoding="utf-8")
    assert rps._scan_step_files(plan_path)["Step 1"] == [
        "scripts/project_metrics/tests/test_cost_collector.py",
        "scripts/project_metrics/tests/fixtures/cost/attributed.jsonl",
        "scripts/project_metrics/tests/fixtures/cost/pre_attribution.jsonl",
        "scripts/project_metrics/tests/fixtures/cost/unparsed.jsonl",
        "scripts/project_metrics/tests/fixtures/cost/parent_sourced_synthetic.jsonl",
    ]


def test_a_trailing_comma_continuation_never_swallows_a_following_step_heading(tmp_path):
    """A ``Files:`` line ending in a stray comma must stop gathering
    continuation lines the moment it meets a step heading -- a plan heading
    always opens its own step, even when the previous field never closed."""
    plan_path = tmp_path / "IMPLEMENTATION_PLAN.md"
    plan_path.write_text(
        "### Step 1: a\n**Files**: scripts/a.py,\n### Step 2: b\n**Files**: scripts/b.py\n",
        encoding="utf-8",
    )
    files = rps._scan_step_files(plan_path)
    assert files["Step 1"] == ["scripts/a.py"]
    assert files["Step 2"] == ["scripts/b.py"]


def test_reconcile_never_credits_a_heading_swallowed_continuation_files_step_to_the_earlier_one(
    tmp_path,
):
    """Production-shape regression: with the trailing-comma plan shape above,
    only Step 2's own file is committed -- Step 1 must not read
    verified-complete from a file it never declared, and Step 2 must."""
    repo_root = tmp_path / "repo"
    base_sha = _seed_repo(repo_root)
    plan = "### Step 1: a\n**Files**: scripts/a.py,\n### Step 2: b\n**Files**: scripts/b.py\n"
    wip = "- [x] Step 1: a\n- [x] Step 2: b\n"
    _setup(repo_root, wip, plan)
    _commit(repo_root, "scripts/b.py", "# b\n")

    out = rps.reconcile(
        SLUG, repo_root, base_sha, _wal_rows_override=[], _test_status_override="green"
    )
    assert _verdict_for(out, "Step 1")["verdict"] != "verified-complete"
    assert _verdict_for(out, "Step 2")["verdict"] == "verified-complete"


# --- a declared glob matches only under its own directory -------------------


def test_path_match_anchored_glob_never_falls_back_to_a_bare_basename_match():
    """A glob's own trailing ``*`` must not become a wildcard for any filename
    anywhere in the repo once its directory prefix stops matching."""
    assert rps._path_match(
        "eval/tests/fixtures/scenarios/*", "eval/tests/fixtures/scenarios/foo.yaml"
    )
    assert not rps._path_match("eval/tests/fixtures/scenarios/*", "unrelated/other/x.py")


# --- production call shape: a real git repo drives the same anchored-glob fix -


def _run_git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _git_capture(args: list[str], cwd: Path) -> str:
    completed = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return completed.stdout.strip()


def test_reconcile_never_confirms_a_step_from_a_file_that_only_matches_a_globs_basename(tmp_path):
    """Through ``reconcile()``'s own production call shape, over a real git
    repo -- not just the ``_path_match`` unit. A step declaring a glob must
    stay unconfirmed when the only real change lives outside the glob's
    directory, even though the change's basename incidentally matches ``*``."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    _run_git(["init", "-q"], repo_root)
    _run_git(["config", "user.email", "test@example.com"], repo_root)
    _run_git(["config", "user.name", "Test User"], repo_root)
    (repo_root / "README.md").write_text("seed\n", encoding="utf-8")
    _run_git(["add", "README.md"], repo_root)
    _run_git(["commit", "-q", "-m", "seed"], repo_root)
    base_sha = _git_capture(["rev-parse", "HEAD"], repo_root)

    plan = (
        "### Step 1: Add scenario fixtures\n"
        "**Files**: eval/tests/fixtures/scenarios/*\n"
        "**Done when**: fixtures land\n"
    )
    _setup(repo_root, "- [x] Step 1: add scenario fixtures\n", plan)

    (repo_root / "unrelated" / "other").mkdir(parents=True)
    (repo_root / "unrelated" / "other" / "x.py").write_text("# unrelated\n", encoding="utf-8")
    _run_git(["add", "unrelated/other/x.py"], repo_root)
    _run_git(["commit", "-q", "-m", "unrelated change"], repo_root)

    out = rps.reconcile(
        SLUG, repo_root, base_sha, _wal_rows_override=[], _test_status_override="green"
    )
    verdict = _verdict_for(out, "Step 1")
    assert verdict["verdict"] != "verified-complete", (
        "an unrelated file must not confirm a glob-declared Files: field via "
        "basename-only fallback matching"
    )


# --- shared-file attribution: only the earliest declarer gets the evidence --


def _seed_repo(repo_root: Path) -> str:
    """A single-commit repo; returns the seed commit's sha as the diff base."""
    repo_root.mkdir()
    _run_git(["init", "-q"], repo_root)
    _run_git(["config", "user.email", "test@example.com"], repo_root)
    _run_git(["config", "user.name", "Test User"], repo_root)
    (repo_root / "README.md").write_text("seed\n", encoding="utf-8")
    _run_git(["add", "README.md"], repo_root)
    _run_git(["commit", "-q", "-m", "seed"], repo_root)
    return _git_capture(["rev-parse", "HEAD"], repo_root)


_TWO_STEPS_SHARE_ONE_FILE = (
    "### Step 1: Build the thing\n**Files**: f.py\n### Step 2: Extend the thing\n**Files**: f.py\n"
)


def test_reconcile_second_declarer_of_a_shared_file_stays_pending_when_only_the_first_is_committed(
    tmp_path,
):
    """td-238(3) through the production call shape: two steps both declare
    `f.py`; only the earlier step's work is committed and the WIP honestly
    shows the later step as not started. The later step has no attributable
    file of its own -- it must stay pending, never verified-complete from a
    file it never touched."""
    repo_root = tmp_path / "repo"
    base_sha = _seed_repo(repo_root)
    _setup(
        repo_root,
        "- [x] Step 1: build the thing\n- [ ] Step 2: extend the thing\n",
        _TWO_STEPS_SHARE_ONE_FILE,
    )
    (repo_root / "f.py").write_text("# step 1 work\n", encoding="utf-8")
    _run_git(["add", "f.py"], repo_root)
    _run_git(["commit", "-q", "-m", "step 1 work"], repo_root)

    out = rps.reconcile(
        SLUG, repo_root, base_sha, _wal_rows_override=[], _test_status_override="green"
    )
    assert _verdict_for(out, "Step 1")["verdict"] == "verified-complete"
    assert _verdict_for(out, "Step 2")["verdict"] == "pending"


def test_reconcile_earliest_declarer_absorbs_a_later_declarers_out_of_order_work(tmp_path):
    """A declared limit of earliest-declarer attribution: plan order is assumed to equal execution order for a shared file. When the
    real work happens out of order -- the later declarer's agent commits the
    file first, while the earlier declarer was never touched -- the earlier
    declarer still absorbs the file as its own attributable evidence and reads
    verified-complete despite never being worked on, while the step that did
    the real work has no attributable file of its own and reads unknown. This
    is a declared limit, not a defect this reconciler guards against: the
    reversal trigger names it, and the full verifier remains the downstream
    correctness backstop for exactly this case."""
    # A unit-level encoding (no real git repo needed): the shared changeset
    # only reflects that `f.py` changed, never which step's agent wrote it --
    # so this is exercised through `reconcile()`'s override hooks, the same
    # production entry point, without the git-repo ceremony this particular
    # case does not depend on.
    root = _setup(
        tmp_path,
        "- [ ] Step 1: build the thing\n- [x] Step 2: extend the thing\n",
        _TWO_STEPS_SHARE_ONE_FILE,
    )
    out = rps.reconcile(
        SLUG,
        root,
        None,
        _changed_files_override=["f.py"],
        _wal_rows_override=[],
        _test_status_override="green",
    )
    assert _verdict_for(out, "Step 1")["verdict"] == "verified-complete"
    assert _verdict_for(out, "Step 2")["verdict"] == "unknown"


def test_reconcile_verifies_two_steps_whose_declared_files_are_never_shared(tmp_path):
    """Regression lock: attribution only withholds evidence for a genuinely
    shared file. Two steps with distinct declared files are judged exactly as
    before attribution landed."""
    root = _setup(
        tmp_path,
        "- [x] Step 1: build a\n- [x] Step 2: build b\n",
        "### Step 1: Build A\n**Files**: a.py\n### Step 2: Build B\n**Files**: b.py\n",
    )
    out = rps.reconcile(
        SLUG,
        root,
        None,
        _changed_files_override=["a.py", "b.py"],
        _wal_rows_override=[],
        _test_status_override="green",
    )
    assert _verdict_for(out, "Step 1")["verdict"] == "verified-complete"
    assert _verdict_for(out, "Step 2")["verdict"] == "verified-complete"


# --- letter-suffixed step ids are their own steps, not merged into the parent -

# Verbatim excerpt: `sidecar-placement/sidecar-placement/IMPLEMENTATION_PLAN.md`
# -- a plan heading and its own `Files:` field, immediately followed by a
# lettered addendum heading and its own, different `Files:` field.
_SIDECAR_PLACEMENT_1B_EXCERPT = (
    "### Step 1: State-repository resolver — mount-aware placement sum type "
    "[Architecture] [parallel-group: A]\n"
    "**Files**: `scripts/_state_repo.py`\n"
    "\n---\n\n"
    "### Step 1b: State-repository resolver tests [parallel-group: A] [depends-on: none]\n"
    "**Files**: `scripts/test_state_repo.py`, `.ai-state/TEST_TOPOLOGY.md` (own\n"
    "`selectors`/`file_dependencies` entry inside `scripts-core`)\n"
)


def test_scan_step_files_keeps_a_lettered_addendum_heading_as_its_own_step(tmp_path):
    plan_path = tmp_path / "IMPLEMENTATION_PLAN.md"
    plan_path.write_text(_SIDECAR_PLACEMENT_1B_EXCERPT, encoding="utf-8")
    files = rps._scan_step_files(plan_path)
    assert files["Step 1"] == ["scripts/_state_repo.py"]
    assert files["Step 1b"] == [
        "scripts/test_state_repo.py",
        ".ai-state/TEST_TOPOLOGY.md",
    ]


def test_parse_wip_steps_recognizes_a_letter_suffixed_checklist_claim(tmp_path):
    wip = "- [x] Step 1b: state-repo resolver tests\n- [ ] Step 1: state-repo resolver\n"
    p = tmp_path / "WIP.md"
    p.write_text(wip, encoding="utf-8")
    assert rps._parse_wip_steps(p) == {"Step 1": "PENDING", "Step 1b": "COMPLETE"}


def test_reconcile_orders_letter_suffixed_and_multi_digit_steps_in_grammar_order(tmp_path):
    plan = (
        "### Step 1: A\n**Files**: a.py\n"
        "### Step 1b: A tests\n**Files**: b.py\n"
        "### Step 2: B\n**Files**: c.py\n"
        "### Step 10: J\n**Files**: d.py\n"
    )
    wip = "- [ ] Step 1: a\n- [ ] Step 1b: a tests\n- [ ] Step 2: b\n- [ ] Step 10: j\n"
    root = _setup(tmp_path, wip, plan)
    out = rps.reconcile(
        SLUG,
        root,
        None,
        _changed_files_override=[],
        _wal_rows_override=[],
        _test_status_override="absent",
    )
    assert [v["step"] for v in out] == ["Step 1", "Step 1b", "Step 2", "Step 10"]


# --- a table-only WIP reconciles, instead of the pre-claim-source "no WIP" ---


def _commit(repo_root: Path, rel_path: str, content: str) -> None:
    path = repo_root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _run_git(["add", rel_path], repo_root)
    _run_git(["commit", "-q", "-m", f"write {rel_path}"], repo_root)


# Verbatim excerpt: sidecar-placement/sidecar-placement's WIP status table.
_STATUS_TABLE_WIP = (
    "| Step | Assignee | Status | Files |\n"
    "|---|---|---|---|\n"
    "| 1 | implementer | complete (GREEN -- 21 passed; self-review clean) "
    "| `scripts/_state_repo.py` |\n"
)


def test_reconcile_a_table_only_wip_reconciles_instead_of_reporting_no_steps(tmp_path):
    """Today ``reconcile()`` returns ``[]`` for a table-only WIP -- its own
    claim parser recognizes only checklist lines, so a table-only file yields
    zero claims and the whole reconciliation short-circuits before touching
    git. Once claim parsing moves to the shared module's three-source reader,
    a table row is a first-class claim source and the step reconciles like
    any other."""
    repo_root = tmp_path / "repo"
    base_sha = _seed_repo(repo_root)
    plan = "### Step 1: State-repository resolver\n**Files**: scripts/_state_repo.py\n"
    _setup(repo_root, _STATUS_TABLE_WIP, plan)
    _commit(repo_root, "scripts/_state_repo.py", "# resolver\n")

    out = rps.reconcile(
        SLUG, repo_root, base_sha, _wal_rows_override=[], _test_status_override="green"
    )
    assert out != []
    assert _verdict_for(out, "Step 1")["verdict"] == "verified-complete"


def test_reconcile_a_stale_complete_table_claim_with_no_file_change_reads_mismatch(tmp_path):
    """A table row claiming a bracketed COMPLETE whose declared file never
    changed is the truncation signature (ground truth contradicts a finished
    claim) -- it must read mismatch, not the honest-not-complete-claim
    pending path, which today's narrower status-table vocabulary produces by
    misreading `[COMPLETE]` as AMBIGUOUS instead of COMPLETE."""
    repo_root = tmp_path / "repo"
    base_sha = _seed_repo(repo_root)
    wip = (
        "| Step | Assignee | Status | Files |\n"
        "|---|---|---|---|\n"
        "| 1 | implementer | [COMPLETE] | f.py |\n"
    )
    plan = "### Step 1: Build the thing\n**Files**: f.py\n"
    _setup(repo_root, wip, plan)

    out = rps.reconcile(
        SLUG, repo_root, base_sha, _wal_rows_override=[], _test_status_override="green"
    )
    assert _verdict_for(out, "Step 1")["verdict"] == "mismatch"


# --- per-step test status: each step reads its own latest run --------------

_CORPUS_FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent
    / "tests"
    / "fixtures"
    / "test_results_step_sections_corpus.md"
)
_P3_5_TEST_RESULTS_MD = _CORPUS_FIXTURE_PATH.read_text(encoding="utf-8")


def test_reconcile_a_steps_own_red_run_is_cleared_by_a_later_green_run_elsewhere_in_the_file(
    tmp_path,
):
    """Per the spec, an own red run is superseded by ANY green run recorded
    later in the document -- not only a later run of the same step. Step 1's
    own only recorded run in the harvested corpus is red (``pass=126
    fail=1``), but the corpus continues with real green work afterward (Step
    2's own run among it), so Step 1's red is cleared. This is the spec's own
    counterexample to a narrower "own green only" reading: a RED
    test-authoring step whose suite goes red on day one stays confirmable once
    later work in the same file proves green, rather than reading red forever."""
    repo_root = tmp_path / "repo"
    base_sha = _seed_repo(repo_root)
    plan = "### Step 1: A\n**Files**: a.py\n### Step 2: B\n**Files**: b.py\n"
    wip = "- [x] Step 1: a\n- [x] Step 2: b\n"
    _setup(repo_root, wip, plan)
    (repo_root / ".ai-work" / SLUG / "TEST_RESULTS.md").write_text(
        _P3_5_TEST_RESULTS_MD, encoding="utf-8"
    )
    _commit(repo_root, "a.py", "# a\n")
    _commit(repo_root, "b.py", "# b\n")

    out = rps.reconcile(SLUG, repo_root, base_sha, _wal_rows_override=[])
    assert _verdict_for(out, "Step 1")["verdict"] == "verified-complete"
    assert _verdict_for(out, "Step 2")["verdict"] == "verified-complete"


def test_reconcile_a_final_red_block_with_no_later_green_stays_red_while_earlier_steps_confirm(
    tmp_path,
):
    """The spec's own boundary case: a RED test-authoring step recorded
    before its GREEN implementation partner has landed -- the file's LAST
    block is genuinely red, with no later green anywhere to supersede it, so
    it stays red. Earlier steps are unaffected either way: a later red never
    clears an earlier green, and an earlier own red (Step 1) is still cleared
    by Step 2's later green, exactly as in the flagship corpus case above."""
    repo_root = tmp_path / "repo"
    base_sha = _seed_repo(repo_root)
    plan = (
        "### Step 1: A\n**Files**: a.py\n"
        "### Step 2: B\n**Files**: b.py\n"
        "### Step 3: RED test-authoring\n**Files**: c.py\n"
    )
    wip = "- [x] Step 1: a\n- [x] Step 2: b\n- [x] Step 3: red test-authoring\n"
    _setup(repo_root, wip, plan)
    test_results = (
        "## Step 1\nResult: pass=0 fail=5 skip=0\n"
        "## Step 2\nResult: pass=20 fail=0 skip=0\n"
        "## Step 3\nResult: pass=0 fail=3 skip=0\n"
    )
    (repo_root / ".ai-work" / SLUG / "TEST_RESULTS.md").write_text(test_results, encoding="utf-8")
    _commit(repo_root, "a.py", "# a\n")
    _commit(repo_root, "b.py", "# b\n")
    _commit(repo_root, "c.py", "# c\n")

    out = rps.reconcile(SLUG, repo_root, base_sha, _wal_rows_override=[])
    assert _verdict_for(out, "Step 1")["verdict"] == "verified-complete"
    assert _verdict_for(out, "Step 2")["verdict"] == "verified-complete"
    assert _verdict_for(out, "Step 3")["verdict"] != "verified-complete"


def _reconcile_with_test_results(tmp_path: Path, test_results: str) -> list[dict]:
    """One committed file, one step claiming it, a synthetic TEST_RESULTS.md --
    shared arrangement for the per-step Result-line contract cases below."""
    repo_root = tmp_path / "repo"
    base_sha = _seed_repo(repo_root)
    plan = "### Step 1: Build the thing\n**Files**: f.py\n"
    wip = "- [x] Step 1: build the thing\n"
    _setup(repo_root, wip, plan)
    (repo_root / ".ai-work" / SLUG / "TEST_RESULTS.md").write_text(test_results, encoding="utf-8")
    _commit(repo_root, "f.py", "# work\n")
    return rps.reconcile(SLUG, repo_root, base_sha, _wal_rows_override=[])


def test_reconcile_a_later_own_green_run_clears_an_earlier_own_red_run_for_the_same_step(
    tmp_path,
):
    """A second, later step's own red block sits after Step 1's red-then-green
    pair in document order -- under global last-line-wins this would flip
    Step 1 to red too, since the file's very last recorded run is red. Per-step
    status must judge Step 1 only by its own (green) latest run."""
    repo_root = tmp_path / "repo"
    base_sha = _seed_repo(repo_root)
    plan = (
        "### Step 1: Build the thing\n**Files**: f.py\n### Step 2: Build another\n**Files**: g.py\n"
    )
    wip = "- [x] Step 1: build the thing\n- [ ] Step 2: build another\n"
    _setup(repo_root, wip, plan)
    test_results = (
        "## Step 1\nResult: pass=5 fail=2 skip=0\n"
        "## Step 1 (retry)\nResult: pass=10 fail=0 skip=0\n"
        "## Step 2\nResult: pass=3 fail=1 skip=0\n"
    )
    (repo_root / ".ai-work" / SLUG / "TEST_RESULTS.md").write_text(test_results, encoding="utf-8")
    _commit(repo_root, "f.py", "# work\n")

    out = rps.reconcile(SLUG, repo_root, base_sha, _wal_rows_override=[])
    assert _verdict_for(out, "Step 1")["verdict"] == "verified-complete"


def test_reconcile_an_all_zero_result_line_reads_red_not_a_confirmed_pass(tmp_path):
    test_results = "## Step 1\nResult: pass=0 fail=0 skip=0\n### Failures\nModuleNotFoundError\n"
    out = _reconcile_with_test_results(tmp_path, test_results)
    assert _verdict_for(out, "Step 1")["verdict"] != "verified-complete"


def test_reconcile_a_later_malformed_result_line_never_clears_an_earlier_red_run(tmp_path):
    """A ``Result:`` line naming a count in prose rather than
    ``pass=``/``fail=`` keys is malformed and contributes no evidence -- it
    must never launder an earlier own red run into a false confirmation."""
    test_results = "## Step 1\nResult: pass=5 fail=2 skip=0\n## Step 1 (later)\nResult: 23 passed\n"
    out = _reconcile_with_test_results(tmp_path, test_results)
    assert _verdict_for(out, "Step 1")["verdict"] != "verified-complete"


def test_reconcile_a_later_declared_no_run_line_never_clears_an_earlier_red_run(tmp_path):
    test_results = "## Step 1\nResult: pass=5 fail=2 skip=0\n## Step 1 (later)\nResult: none\n"
    out = _reconcile_with_test_results(tmp_path, test_results)
    assert _verdict_for(out, "Step 1")["verdict"] != "verified-complete"


def test_reconcile_preexisting_failures_never_block_verified_complete(tmp_path):
    test_results = "## Step 1\nResult: pass=10 fail=0 skip=0 preexisting=2\n"
    out = _reconcile_with_test_results(tmp_path, test_results)
    assert _verdict_for(out, "Step 1")["verdict"] == "verified-complete"


# --- attribution: pins keeping earliest-declarer safe against re-opening ----
# --- td-238(3) (both regression locks -- pass on current code) --------------


def test_reconcile_a_fix_commit_on_the_earlier_declarer_never_verifies_the_later_declarer(
    tmp_path,
):
    """A rework/fix commit on the shared file, made by the earlier declarer,
    must not be misread as the later declarer's own work. The later declarer
    stays pending, never verified-complete, and never gets an unwarranted
    auto-mark."""
    repo_root = tmp_path / "repo"
    base_sha = _seed_repo(repo_root)
    plan = _TWO_STEPS_SHARE_ONE_FILE
    wip = "- [x] Step 1: build the thing\n- [ ] Step 2: extend the thing\n"
    _setup(repo_root, wip, plan)
    (repo_root / "f.py").write_text("# step 1 work\n", encoding="utf-8")
    _run_git(["add", "f.py"], repo_root)
    _run_git(["commit", "-q", "-m", "step 1 work"], repo_root)
    (repo_root / "f.py").write_text("# step 1 work, fixed\n", encoding="utf-8")
    _run_git(["add", "f.py"], repo_root)
    _run_git(["commit", "-q", "-m", "step 1 fix"], repo_root)

    out = rps.reconcile(
        SLUG, repo_root, base_sha, _wal_rows_override=[], _test_status_override="green"
    )
    verdict = _verdict_for(out, "Step 2")
    assert verdict["verdict"] == "pending"
    assert verdict["needs_mark"] is False


def test_reconcile_a_serial_lane_of_four_steps_on_one_file_only_verifies_the_first(tmp_path):
    """A serial-lane shape (one file edited across several consecutive steps,
    all committed): only the earliest declarer is confirmable. Every later
    declarer reads unknown, and the CLI's exit code reflects the owed human
    verification (2), not a clean recovery-needed (1)."""
    repo_root = tmp_path / "repo"
    base_sha = _seed_repo(repo_root)

    plan = (
        "### Step 1: A\n**Files**: f.py\n"
        "### Step 2: B\n**Files**: f.py\n"
        "### Step 3: C\n**Files**: f.py\n"
        "### Step 4: D\n**Files**: f.py\n"
    )
    wip = "- [x] Step 1: a\n- [x] Step 2: b\n- [x] Step 3: c\n- [x] Step 4: d\n"  # id-citation-discipline:ignore
    _setup(repo_root, wip, plan)
    _commit(repo_root, "f.py", "# work\n")

    code = rps.main([SLUG, "--repo-root", str(repo_root), "--base-ref", base_sha, "--quiet"])
    out = rps.reconcile(
        SLUG, repo_root, base_sha, _wal_rows_override=[], _test_status_override="green"
    )
    assert _verdict_for(out, "Step 1")["verdict"] == "verified-complete"
    assert _verdict_for(out, "Step 2")["verdict"] == "unknown"
    assert _verdict_for(out, "Step 3")["verdict"] == "unknown"
    assert _verdict_for(out, "Step 4")["verdict"] == "unknown"
    assert code == 2


# --- The unknown evidence names every earlier declarer, not just one ----


def test_unknown_evidence_names_every_earlier_declarer_when_files_are_split_across_two(
    tmp_path,
):
    """A step whose two declared files are absorbed by two *different* earlier
    steps must have both named in its evidence -- naming only the first found
    leaves a human reader unable to settle the claim for the other file."""
    repo_root = tmp_path / "repo"
    base_sha = _seed_repo(repo_root)
    plan = (
        "### Step 1: A\n**Files**: a.py\n"
        "### Step 2: B\n**Files**: b.py\n"
        "### Step 3: C\n**Files**: a.py, b.py\n"
    )
    wip = "- [x] Step 1: a\n- [x] Step 2: b\n- [x] Step 3: c\n"  # id-citation-discipline:ignore
    _setup(repo_root, wip, plan)
    _commit(repo_root, "a.py", "# a\n")
    _commit(repo_root, "b.py", "# b\n")

    out = rps.reconcile(
        SLUG, repo_root, base_sha, _wal_rows_override=[], _test_status_override="green"
    )
    verdict = _verdict_for(out, "Step 3")
    assert verdict["verdict"] == "unknown"
    assert "Step 1" in verdict["evidence"]  # id-citation-discipline:ignore
    assert "Step 2" in verdict["evidence"]  # id-citation-discipline:ignore


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
